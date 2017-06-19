import os
import shutil
import subprocess
import random
import pymongo

import virtool.utils
import virtool.pathoscope
import virtool.job

PATHOSCOPE_TASK_NAMES = ["pathoscope_bowtie"]


LIST_PROJECTION = [
    "_id",
    "name",
    "host",
    "isolate",
    "added",
    "user_id",
    "imported",
    "archived",
    "pathoscope",
    "nuvs"
]


def processor(document):
    document = dict(document)
    document["sample_id"] = document.pop("_id")
    return document


projector = [
    "_id",
    "name",
    "added",
    "username",
    "imported",
    "archived",
    "pathoscope",
    "nuvs",
    "group",
    "group_read",
    "group_write",
    "all_read",
    "all_write"
]


def calculate_algorithm_tags(analyses):
    update = {
        "pathoscope": False,
        "nuvs": False
    }

    pathoscope = list()
    nuvs = list()

    for analysis in analyses:
        if analysis["algorithm"] in PATHOSCOPE_TASK_NAMES:
            pathoscope.append(analysis)

        if analysis["algorithm"] == "nuvs":
            nuvs.append(analysis)

    if len(pathoscope) > 0:
        update["pathoscope"] = any([document["ready"] for document in pathoscope]) or "ip"

    if len(nuvs) > 0:
        update["nuvs"] = any([document["ready"] for document in nuvs]) or "ip"

    return update


async def recalculate_algorithm_tags(db, sample_id):
    analyses = await db.analyses.find({"sample_id": sample_id}, ["ready", "algorithm"]).to_list(None)

    update = calculate_algorithm_tags(analyses)

    await db.samples.update({"_id": sample_id}, {"$set": update})


async def get_sample_owner(db, sample_id):
    return (await db.users.find_one(sample_id, "user_id"))["user_id"]


async def set_quality(db, sample_id, quality):
    """
    Populates the ``quality`` field of the document with data generated by FastQC. Data includes GC content, read
    length ranges, and detailed quality data. Also sets the ``imported`` field to ``True``.

    Called from an :class:`.ImportReads` job.

    :param db: a Motor client
    :type db: :class:`.motor.motor_asyncio.AsyncIOMotorClient``
    
    :param sample_id: the id of the sample to set quality for
    :type sample_id: str
    
    :param quality: the quality data to attach to the sample document
    :type quality: dict

    """
    return await db.samples.find_one_and_update(sample_id, {
        "$set": {
            "quality": quality,
            "imported": True
        }
    }, return_document=pymongo.ReturnDocument.AFTER)


async def remove_samples(db, settings, id_list):
    """
    Complete removes the samples identified by the document ids in ``id_list``. In order, it:

    - removes all analyses associated with the sample from the analyses collection
    - removes the sample from the samples collection
    - removes the sample directory from the file system
    
    :param db: a Motor client
    :type db: :class:`.motor.motor_asyncio.AsyncIOMotorClient``
    
    :param settings: a Virtool settings object
    :type settings: :class:`.Settings`

    :param id_list: a list sample ids to remove
    :type id_list: list

    :return: the response from the samples collection remove operation
    :rtype: dict

    """
    # Remove all analysis documents associated with the sample.
    db.analyses.remove({"_id": {
        "$in": id_list
    }})

    # Remove the samples described by id_list from the database.
    result = await db.samples.remove({"_id": {
        "$in": id_list
    }})

    samples_path = os.path.join(settings.get("data_path"), "samples")

    for sample_id in id_list:
        try:
            await virtool.utils.rm(os.path.join(samples_path, "sample_" + sample_id), recursive=True)
        except FileNotFoundError:
            pass

    return result


class ImportReads(virtool.job.Job):

    """
    A subclass of :class:`~.job.Job` that creates a new sample by importing reads from the watch directory. Has the
    stages:

    1. mk_sample_dir
    2. import_files
    3. trim_reads
    4. save_trimmed
    5. fastqc
    6. parse_fastqc
    7. clean_watch

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #: The id assigned to the new sample.
        self.sample_id = self._task_args["_id"]

        #: The path where the files for this sample are stored.
        self.sample_path = self._settings.get("data_path") + "/samples/sample_" + str(self.sample_id)

        #: The names of the reads files in the watch path used to create the sample.
        self.files = self._task_args["files"]

        #: Is the sample library paired or not.
        self.paired = self._task_args["paired"]

        #: The ordered list of :ref:`stage methods <stage-methods>` that are called by the job.
        self.stage_list = [
            self.mk_sample_dir,
            self.trim_reads,
            self.save_trimmed,
            self.fastqc,
            self.parse_fastqc,
            self.clean_watch
        ]

    @virtool.job.stage_method
    def mk_sample_dir(self):
        """
        Make a data directory for the sample. Read files, quality data from FastQC, and analysis data will be stored
        here.

        """
        try:
            os.makedirs(os.path.join(self.sample_path, "analysis"))
        except OSError:
            shutil.rmtree(self.sample_path)
            os.makedirs(os.path.join(self.sample_path, "analysis"))

    @virtool.job.stage_method
    def trim_reads(self):
        input_paths = [os.path.join(self._settings.get("data_path"), "files", filename) for filename in self.files]

        command = [
            "skewer",
            "-m", "pe" if self.paired else "head",
            "-l", "50",
            "-q", "20",
            "-Q", "25",
            "-t", str(self._settings.get("import_reads_proc")),
            "-o", os.path.join(self.sample_path, "reads"),
        ] + input_paths

        # Prevents an error from skewer when calls inside a subprocess.
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = "/usr/lib/x86_64-linux-gnu"

        self.run_process(command, dont_read_stdout=True, env=env)

    @virtool.job.stage_method
    def save_trimmed(self):
        """
        Give the trimmed FASTQ and log files generated by skewer more readable names.

        """
        if self.paired:
            shutil.move(
                os.path.join(self.sample_path, "reads-trimmed-pair1.fastq"),
                os.path.join(self.sample_path, "reads_1.fastq")
            )

            shutil.move(
                os.path.join(self.sample_path, "reads-trimmed-pair2.fastq"),
                os.path.join(self.sample_path, "reads_2.fastq")
            )

        else:
            shutil.move(
                os.path.join(self.sample_path, "reads-trimmed.fastq"),
                os.path.join(self.sample_path, "reads_1.fastq")
            )

        shutil.move(
            os.path.join(self.sample_path, "reads-trimmed.log"),
            os.path.join(self.sample_path, "trim.log")
        )

    @virtool.job.stage_method
    def fastqc(self):
        """
        Runs FastQC on the renamed, trimmed read files.

        """
        os.mkdir(self.sample_path + "/fastqc")

        command = [
            "fastqc",
            "-f", "fastq",
            "-o", os.path.join(self.sample_path, "fastqc"),
            "-t", "2",
            "--extract",
            self.sample_path + "/reads_1.fastq"
        ]

        if self.paired:
            command.append(os.path.join(self.sample_path, "reads_2.fastq"))

        self.run_process(command)

    @virtool.job.stage_method
    def parse_fastqc(self):
        """
        Capture the desired data from the FastQC output. The data is added to the samples database
        in the main run() method

        """
        # Get the text data files from the FastQC output
        for name in os.listdir(self.sample_path + "/fastqc"):
            if "reads" in name and "." not in name:
                suffix = name.split("_")[1]
                folder = self.sample_path + "/fastqc/" + name
                shutil.move(folder + "/fastqc_data.txt", self.sample_path + "/fastqc_" + suffix + ".txt")

        # Dispose of the rest of the data files.
        shutil.rmtree(self.sample_path + "/fastqc")

        fastqc = {
            "count": 0
        }

        # Parse data file(s)
        for suffix in [1, 2]:
            try:
                # Open a FastQC data file and begin parsing it
                with open(self.sample_path + "/fastqc_" + str(suffix) + ".txt") as data:
                    # This is flag is set when a multi-line FastQC section is found. It is set to None when the section
                    # ends and is the default value when the parsing loop beings
                    flag = None

                    for line in data:
                        # Turn off flag if the end of a module is encountered
                        if flag is not None and "END_MODULE" in line:
                            flag = None

                        # Total sequences
                        elif "Total Sequences" in line:
                            fastqc["count"] += int(line.split("\t")[1])

                        # Read encoding (eg. Illumina 1.9)
                        elif "encoding" not in fastqc and "Encoding" in line:
                            fastqc["encoding"] = line.split("\t")[1]

                        # Length
                        elif "Sequence length" in line:
                            length = [int(s) for s in line.split("\t")[1].split('-')]

                            if suffix == 1:
                                fastqc["length"] = length
                            else:
                                fastqc["length"] = [
                                    min([fastqc["length"][0], length[0]]),
                                    max([fastqc["length"][1], length[1]])
                                ]

                        # GC-content
                        elif "%GC" in line and "#" not in line:
                            gc = float(line.split("\t")[1])

                            if suffix == 1:
                                fastqc["gc"] = gc
                            else:
                                fastqc["gc"] = (fastqc["gc"] + gc) / 2

                        # The statements below handle the beginning of multi-line FastQC sections. They set the flag
                        # value to the found section and allow it to be further parsed.
                        elif "Per base sequence quality" in line:
                            flag = "bases"
                            if suffix == 1:
                                fastqc[flag] = [None] * fastqc["length"][1]

                        elif "Per sequence quality scores" in line:
                            flag = "sequences"
                            if suffix == 1:
                                fastqc[flag] = [0] * 50

                        elif "Per base sequence content" in line:
                            flag = "composition"
                            if suffix == 1:
                                fastqc[flag] = [None] * fastqc["length"][1]

                        # The statements below handle the parsing of lines when the flag has been set for a multi-line
                        # section. This ends when the 'END_MODULE' line is encountered and the flag is reset to none
                        elif flag in ["composition", "bases"] and "#" not in line:
                            # Split line around whitespace.
                            split = line.rstrip().split()

                            # Convert all fields except first to 2-decimal floats.
                            values = [round(int(value.split(".")[0]), 1) for value in split[1:]]

                            # Convert to position field to a one- or two-member tuple.
                            pos = [int(x) for x in split[0].split('-')]

                            if len(pos) > 1:
                                pos = range(pos[0], pos[1] + 1)
                            else:
                                pos = [pos[0]]

                            if suffix == 1:
                                for i in pos:
                                    fastqc[flag][i - 1] = values
                            else:
                                for i in pos:
                                    fastqc[flag][i - 1] = virtool.utils.average_list(fastqc[flag][i - 1], values)

                        elif flag == "sequences" and "#" not in line:
                            line = line.rstrip().split()

                            quality = int(line[0])

                            fastqc["sequences"][quality] += int(line[1].split(".")[0])

            # No suffix of 2 will be present for single-end samples
            except IOError:
                pass

        self.collection_operation("samples", "set_stats", {
            "_id": self.sample_id,
            "fastqc": fastqc
        })

    @virtool.job.stage_method
    def clean_watch(self):
        """ Try to remove the original read files from the watch directory """
        self.collection_operation("files", "_remove_files", {"to_remove": self.files})

    @virtool.job.stage_method
    def cleanup(self):
        """
        This method is run in the event of an error or cancellation signal. It deletes the sample directory
        and wipes the sample information from the samples_db collection. Watch files are not deleted.

        """
        # Delete database entry
        self.collection_operation("files", "reserve_files_cop", {"file_ids": self.files, "reserved": False})
        self.collection_operation("samples", "_remove_samples", [self.sample_id])


def check_collection(db_name, data_path, host="localhost", port=27017):
    db = pymongo.MongoClient(host, port)[db_name]

    response = {
        "orphaned_analyses": list(),
        "missing_analyses": list(),
        "orphaned_samples": list(),
        "mismatched_samples": list(),
    }

    existing_analyses = [entry["_id"] for entry in db.analyses.find({}, {"_id": True})]

    aggregated = db.samples.aggregate([
        {"$project": {"analyses": True}},
        {"$unwind": {"path": "$analyses"}}
    ])

    linked_analyses = [result["analyses"] for result in aggregated]

    response["orphaned_analyses"] = list(filter(lambda x: x not in linked_analyses, existing_analyses))
    response["missing_analyses"] = list(filter(lambda x: x not in existing_analyses, linked_analyses))

    db_samples = {entry["_id"]: len(entry["files"]) for entry in db.samples.find({}, {"files": True})}

    fs_samples = dict()

    samples_path = os.path.join(data_path, "samples/")

    for dirname in os.listdir(samples_path):
        sample_files = os.listdir(os.path.join(samples_path, dirname))
        fastq = filter(lambda x: x.endswith("fastq") or x.endswith("fq"), sample_files)
        fs_samples[dirname.replace("sample_", "")] = len(list(fastq))

    response["defiled_samples"] = list(filter(lambda x: x not in fs_samples, db_samples.keys()))

    for sample_id, file_count in fs_samples.items():
        if sample_id not in db_samples:
            response["orphaned_samples"].append(sample_id)
        elif file_count != db_samples[sample_id]:
            response["mismatched_samples"].append(sample_id)

    response["failed"] = len(response["missing_analyses"]) > 0 or len(response["mismatched_samples"]) > 0

    return response


def reduce_library_size(input_path, output_path):
    line_count = subprocess.check_output(["wc", "-l", input_path])
    decoded = line_count.decode("utf-8")

    seq_count = int(int(decoded.split(" ")[0]) / 4)

    if seq_count > 17000000:
        randomized_indexes = random.sample(range(0, seq_count), 17000000)

        randomized_indexes.sort()

        next_read_index = randomized_indexes[0] * 4
        next_index = 1
        line_count = 0
        writing = False

        with open(input_path, "r") as input_file:
            with open(output_path, "w") as output_file:

                for index, line in enumerate(input_file):
                    if index == next_read_index:
                        try:
                            next_read_index = randomized_indexes[next_index] * 4
                            next_index += 1
                            writing = True
                        except IndexError:
                            break

                    if writing:
                        if line_count == 0:
                            assert line.startswith("@")

                        output_file.write(line)
                        line_count += 1

                        if line_count == 4:
                            writing = False
                            line_count = 0

        os.remove(input_path)

    else:
        os.rename(input_path, output_path)


def can_read(document, user_groups):
    return document["all_read"] or (document["group_read"] and document["group"] in user_groups)


def writer(connection, message):

    if message["operation"] not in ["add", "update", "remove"]:
        raise ValueError("samples.writer only takes messages with operations: add, update, remove")

    # A list of groups the connection's user belongs to.
    user_groups = connection.user["groups"]

    data = message["data"]

    if message["operation"] in ["add", "update"]:
        to_send = dict(message)
        to_send["data"] = [d for d in data if can_read(d, user_groups)]

        send_count = len(to_send["data"])

        if send_count:
            connection.write_message(to_send)

        if send_count < len(message["data"]):
            message["data"] = list({d["_id"] for d in data} - set(to_send["data"]))
            message["operation"] = "remove"
            connection.write_message(message)

        return
