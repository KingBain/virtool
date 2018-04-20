import asyncio
import gzip
import json
import os
from copy import deepcopy

import pymongo
import pymongo.errors
from aiohttp import web
from pymongo import ReturnDocument

import virtool.db.history
import virtool.db.refs
import virtool.db.kinds
import virtool.history
import virtool.refs
import virtool.refs
import virtool.kinds
import virtool.utils
import virtool.validators
from virtool.api.utils import bad_request, compose_regex_query, conflict, json_response, no_content, not_found, \
    paginate, protected, unpack_request, validation

SCHEMA_VALIDATOR = {
    "type": "list",
    "validator": virtool.validators.has_unique_segment_names,
    "schema": {
        "type": "dict",
        "allow_unknown": False,
        "schema": {
            "name": {"type": "string", "required": True},
            "required": {"type": "boolean", "default": True},
            "molecule": {"type": "string", "default": "", "allowed": [
                "",
                "ssDNA",
                "dsDNA",
                "ssRNA",
                "ssRNA+",
                "ssRNA-",
                "dsRNA"
            ]}
        }
    }
}


async def find(req):
    """
    Find kinds.

    """
    db = req.app["db"]

    term = req.query.get("find", None)
    verified = req.query.get("verified", None)
    names = req.query.get("names", False)

    db_query = dict()

    if term:
        db_query.update(compose_regex_query(term, ["name", "abbreviation"]))

    if verified is not None:
        db_query["verified"] = virtool.utils.to_bool(verified)

    if names in [True, "true"]:
        data = await db.kinds.find(db_query, ["name"], sort=[("name", 1)]).to_list(None)
        data = [virtool.utils.base_processor(d) for d in data]
    else:
        data = await paginate(db.kinds, db_query, req.query, sort="name", projection=virtool.kinds.LIST_PROJECTION)
        data["modified_count"] = len(await db.history.find({"index.id": "unbuilt"}, ["kind"]).distinct("kind.name"))

    return json_response(data)


async def get(req):
    """
    Get a complete kind document. Joins the kind document with its associated sequence documents.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]

    complete = await virtool.db.kinds.join_and_format(db, kind_id)

    if not complete:
        return not_found()

    return json_response(complete)


@validation({
    "name": {"type": "string", "required": True, "min": 1},
    "abbreviation": {"type": "string", "min": 1},
    "schema": SCHEMA_VALIDATOR
})
async def create(req):
    """
    Add a new kind to the collection. Checks to make sure the supplied kind name and abbreviation are not already in
    use in the collection. Any errors are sent back to the client.

    """
    db, data = req.app["db"], req["data"]

    # Abbreviation defaults to empty string if not provided.
    abbreviation = data.get("abbreviation", "")

    # Check if either the name or abbreviation are already in use. Send a ``409`` to the client if there is a conflict.
    message = await virtool.db.kinds.check_name_and_abbreviation(db, data["name"], abbreviation)

    if message:
        return conflict(message)

    kind_id = await virtool.db.utils.get_new_id(db.kinds)

    # Start building a kind document.
    data.update({
        "_id": kind_id,
        "abbreviation": abbreviation,
        "last_indexed_version": None,
        "verified": False,
        "lower_name": data["name"].lower(),
        "isolates": [],
        "version": 0,
        "schema": []
    })

    # Insert the kind document.
    await db.kinds.insert_one(data)

    # Join the kind document into a complete kind record. This will be used for recording history.
    joined = await virtool.db.kinds.join(db, kind_id, data)

    # Build a ``description`` field for the kind creation change document.
    description = "Created {}".format(data["name"])

    # Add the abbreviation to the description if there is one.
    if abbreviation:
        description += " ({})".format(abbreviation)

    await virtool.db.history.add(
        db,
        "create",
        None,
        joined,
        description,
        req["client"].user_id
    )

    complete = await virtool.db.kinds.join_and_format(db, kind_id, joined=joined)

    await req.app["dispatcher"].dispatch(
        "kinds",
        "update",
        virtool.utils.base_processor({key: joined[key] for key in virtool.kinds.LIST_PROJECTION})
    )

    headers = {
        "Location": "/api/kinds/" + kind_id
    }

    return json_response(complete, status=201, headers=headers)


@validation({
    "name": {"type": "string"},
    "abbreviation": {"type": "string"},
    "schema": SCHEMA_VALIDATOR
})
async def edit(req):
    """
    Edit an existing new kind. Checks to make sure the supplied kind name and abbreviation are not already in use in
    the collection.

    """
    db, data = req.app["db"], req["data"]

    kind_id = req.match_info["kind_id"]

    # Get existing complete kind record, at the same time ensuring it exists. Send a ``404`` if not.
    old = await virtool.db.kinds.join(db, kind_id)

    if not old:
        return not_found()

    name_change = data.get("name", None)
    abbreviation_change = data.get("abbreviation", None)
    schema_change = data.get("schema", None)

    if name_change == old["name"]:
        name_change = None

    old_abbreviation = old.get("abbreviation", "")

    if abbreviation_change == old_abbreviation:
        abbreviation_change = None

    if schema_change == old.get("schema", None):
        schema_change = None

    # Sent back ``200`` with the existing kind record if no change will be made.
    if name_change is None and abbreviation_change is None and schema_change is None:
        return json_response(await virtool.db.kinds.join_and_format(db, kind_id))

    # Make sure new name and/or abbreviation are not already in use.
    message = await virtool.db.kinds.check_name_and_abbreviation(db, name_change, abbreviation_change)

    if message:
        return json_response({"message": message}, status=409)

    # Update the ``modified`` and ``verified`` fields in the kind document now, because we are definitely going to
    # modify the kind.
    data["verified"] = False

    # If the name is changing, update the ``lower_name`` field in the kind document.
    if name_change:
        data["lower_name"] = data["name"].lower()

    # Update the database collection.
    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": data,
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    description = None

    if name_change is not None:
        description = "Changed name to {}".format(new["name"])

        if abbreviation_change is not None:
            # Abbreviation is being removed.
            if abbreviation_change == "" and old_abbreviation:
                description += " and removed abbreviation {}".format(old["abbreviation"])
            # Abbreviation is being added where one didn't exist before
            elif abbreviation_change and not old_abbreviation:
                description += " and added abbreviation {}".format(new["abbreviation"])
            # Abbreviation is being changed from one value to another.
            else:
                description += " and abbreviation to {}".format(new["abbreviation"])

    elif abbreviation_change is not None:
        # Abbreviation is being removed.
        if abbreviation_change == "" and old["abbreviation"]:
            description = "Removed abbreviation {}".format(old_abbreviation)
        # Abbreviation is being added where one didn't exist before
        elif abbreviation_change and not old.get("abbreviation", ""):
            description = "Added abbreviation {}".format(new["abbreviation"])
        # Abbreviation is being changed from one value to another.
        else:
            description = "Changed abbreviation to {}".format(new["abbreviation"])

    if schema_change is not None:
        if description is None:
            description = "Modified schema"
        else:
            description += " and modified schema"

    await virtool.db.history.add(
        db,
        "edit",
        old,
        new,
        description,
        req["client"].user_id
    )

    await req.app["dispatcher"].dispatch(
        "kinds",
        "update",
        virtool.utils.base_processor({key: new[key] for key in virtool.kinds.LIST_PROJECTION})
    )

    return json_response(await virtool.db.kinds.join_and_format(db, kind_id, joined=new, issues=issues))


async def remove(req):
    """
    Remove a kind document and its associated sequence documents.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]

    # Join the kind.
    joined = await virtool.db.kinds.join(db, kind_id)

    if not joined:
        return not_found()

    # Remove all sequences associated with the kind.
    await db.sequences.delete_many({"kind_id": kind_id})

    # Remove the kind document itself.
    await db.kinds.delete_one({"_id": kind_id})

    description = "Removed {}".format(joined["name"])

    if joined["abbreviation"]:
        description += " ({})".format(joined["abbreviation"])

    await virtool.db.history.add(
        db,
        "remove",
        joined,
        None,
        description,
        req["client"].user_id
    )

    await req.app["dispatcher"].dispatch(
        "kinds",
        "remove",
        [kind_id]
    )

    return web.Response(status=204)


async def list_isolates(req):
    """
    Return a list of isolate records for a given kind.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]

    document = await virtool.db.kinds.join_and_format(db, kind_id)

    if not document:
        return not_found()

    return json_response(document["isolates"])


async def get_isolate(req):
    """
    Get a complete specific isolate sub-document, including its sequences.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.kinds.find_one({"_id": kind_id, "isolates.id": isolate_id}, ["isolates"])

    if not document:
        return not_found()

    isolate = dict(virtool.kinds.find_isolate(document["isolates"], isolate_id), sequences=[])

    async for sequence in db.sequences.find({"isolate_id": isolate_id}, {"kind_id": False, "isolate_id": False}):
        sequence["id"] = sequence.pop("_id")
        isolate["sequences"].append(sequence)

    return json_response(isolate)


@validation({
    "source_type": {"type": "string", "default": ""},
    "source_name": {"type": "string", "default": ""},
    "default": {"type": "boolean", "default": False}
})
async def add_isolate(req):
    """
    Add a new isolate to a kind.

    """
    db = req.app["db"]
    settings = req.app["settings"]
    data = req["data"]

    kind_id = req.match_info["kind_id"]

    document = await db.kinds.find_one(kind_id)

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    # True if the new isolate should be default and any existing isolates should be non-default.
    will_be_default = not isolates or data["default"]

    # Get the complete, joined entry before the update.
    old = await virtool.db.kinds.join(db, kind_id, document)

    # All source types are stored in lower case.
    data["source_type"] = data["source_type"].lower()

    if not virtool.kinds.check_source_type(settings, data["source_type"]):
        return conflict("Source type is not allowed")

    # Get a unique isolate_id for the new isolate.
    isolate_id = await virtool.db.kinds.get_new_isolate_id(db)

    # Set ``default`` to ``False`` for all existing isolates if the new one should be default.
    if isolates and data["default"]:
        for isolate in isolates:
            isolate["default"] = False

    # Force the new isolate as default if it is the first isolate.
    if not isolates:
        data["default"] = True

    # Set the isolate as the default isolate if it is the first one.
    data.update({
        "default": will_be_default,
        "id": isolate_id
    })

    isolates.append(data)

    # Push the new isolate to the database.
    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    # Get the joined entry now that it has been updated.
    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, joined=new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.kinds.format_isolate_name(data)

    description = "Added {}".format(isolate_name)

    if will_be_default:
        description += " as default"

    await virtool.db.history.add(
        db,
        "add_isolate",
        old,
        new,
        description,
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    headers = {
        "Location": "/api/kinds/{}/isolates/{}".format(kind_id, isolate_id)
    }

    return json_response(dict(data, sequences=[]), status=201, headers=headers)


@validation({
    "source_type": {"type": "string"},
    "source_name": {"type": "string"}
})
async def edit_isolate(req):
    """
    Edit an existing isolate.

    """
    db = req.app["db"]
    settings = req.app["settings"]
    data = req["data"]

    kind_id = req.match_info["kind_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.kinds.find_one({"_id": kind_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate = virtool.kinds.find_isolate(isolates, isolate_id)

    if not isolate:
        return not_found()

    # All source types are stored in lower case.
    if "source_type" in data:
        data["source_type"] = data["source_type"].lower()

        if settings.get("restrict_source_types") and data["source_type"] not in settings.get("allowed_source_types"):
            return conflict("Not an allowed source type")

    old_isolate_name = virtool.kinds.format_isolate_name(isolate)

    isolate.update(data)

    old = await virtool.db.kinds.join(db, kind_id)

    # Replace the isolates list with the update one.
    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    # Get the joined entry now that it has been updated.
    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, joined=new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.kinds.format_isolate_name(isolate)

    # Use the old and new entry to add a new history document for the change.
    await virtool.db.history.add(
        db,
        "edit_isolate",
        old,
        new,
        "Renamed {} to {}".format(old_isolate_name, isolate_name),
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    complete = await virtool.db.kinds.join_and_format(db, kind_id, joined=new)

    for isolate in complete["isolates"]:
        if isolate["id"] == isolate_id:
            return json_response(isolate, status=200)


async def set_as_default(req):
    """
    Set an isolate as default.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]
    isolate_id = req.match_info["isolate_id"]

    document = await db.kinds.find_one({"_id": kind_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate = virtool.kinds.find_isolate(isolates, isolate_id)

    if not isolate:
        return not_found()

    # Set ``default`` to ``False`` for all existing isolates if the new one should be default.
    for existing_isolate in isolates:
        existing_isolate["default"] = False

    isolate["default"] = True

    if isolates == document["isolates"]:
        complete = await virtool.db.kinds.join_and_format(db, kind_id)
        for isolate in complete["isolates"]:
            if isolate["id"] == isolate_id:
                return json_response(isolate)

    old = await virtool.db.kinds.join(db, kind_id)

    # Replace the isolates list with the updated one.
    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    # Get the joined entry now that it has been updated.
    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, joined=new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.kinds.format_isolate_name(isolate)

    # Use the old and new entry to add a new history document for the change.
    await virtool.db.history.add(
        db,
        "set_as_default",
        old,
        new,
        "Set {} as default".format(isolate_name),
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    complete = await virtool.db.kinds.join_and_format(db, kind_id, new)

    for isolate in complete["isolates"]:
        if isolate["id"] == isolate_id:
            return json_response(isolate)


async def remove_isolate(req):
    """
    Remove an isolate and its sequences from a kind.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]

    document = await db.kinds.find_one(kind_id)

    if not document:
        return not_found()

    isolates = deepcopy(document["isolates"])

    isolate_id = req.match_info["isolate_id"]

    # Get any isolates that have the isolate id to be removed (only one should match!).
    isolate_to_remove = virtool.kinds.find_isolate(isolates, isolate_id)

    if not isolate_to_remove:
        return not_found()

    # Remove the isolate from the kind' isolate list.
    isolates.remove(isolate_to_remove)

    new_default = None

    # Set the first isolate as default if the removed isolate was the default.
    if isolate_to_remove["default"] and len(isolates):
        new_default = isolates[0]
        new_default["default"] = True

    old = await virtool.db.kinds.join(db, kind_id, document)

    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "isolates": isolates,
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, joined=new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    # Remove any sequences associated with the removed isolate.
    await db.sequences.delete_many({"isolate_id": isolate_id})

    description = "Removed {}".format(virtool.kinds.format_isolate_name(isolate_to_remove))

    if isolate_to_remove["default"] and new_default:
        description += " and set {} as default".format(virtool.kinds.format_isolate_name(new_default))

    await virtool.db.history.add(
        db,
        "remove_isolate",
        old,
        new,
        description,
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    return no_content()


async def list_sequences(req):
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]
    isolate_id = req.match_info["isolate_id"]

    if not await db.kinds.find({"_id": kind_id}, {"isolates.id": isolate_id}).count():
        return not_found()

    projection = list(virtool.kinds.SEQUENCE_PROJECTION)

    projection.remove("kind_id")
    projection.remove("isolate_id")

    documents = await db.sequences.find({"isolate_id": isolate_id}, projection).to_list(None)

    return json_response([virtool.utils.base_processor(d) for d in documents])


async def get_sequence(req):
    """
    Get a single sequence document by its ``accession`.

    """
    db = req.app["db"]

    sequence_id = req.match_info["sequence_id"]

    document = await db.sequences.find_one(sequence_id, virtool.kinds.SEQUENCE_PROJECTION)

    if not document:
        return not_found()

    return json_response(virtool.utils.base_processor(document))


@validation({
    "id": {"type": "string", "minlength": 1, "required": True},
    "definition": {"type": "string", "minlength": 1, "required": True},
    "host": {"type": "string"},
    "segment": {"type": "string"},
    "sequence": {"type": "string", "minlength": 1, "required": True}
})
async def create_sequence(req):
    """
    Create a new sequence record for the given isolate.

    """
    db, data = req.app["db"], req["data"]

    # Extract variables from URL path.
    kind_id, isolate_id = (req.match_info[key] for key in ["kind_id", "isolate_id"])

    # Get the subject kind document. Will be ``None`` if it doesn't exist. This will result in a ``404`` response.
    document = await db.kinds.find_one({"_id": kind_id, "isolates.id": isolate_id})

    if not document:
        return not_found("kind or isolate not found")

    segment = data.get("segment", None)

    if segment and segment not in {s["name"] for s in document.get("schema", {})}:
        return not_found("Segment not found")

    # Update POST data to make sequence document.
    data.update({
        "_id": data.pop("id"),
        "kind_id": kind_id,
        "isolate_id": isolate_id,
        "host": data.get("host", ""),
        "segment": segment
    })

    old = await virtool.db.kinds.join(db, kind_id, document)

    try:
        await db.sequences.insert_one(data)
    except pymongo.errors.DuplicateKeyError:
        return conflict("Sequence id already exists")

    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    new = await virtool.db.kinds.join(db, kind_id, document)

    issues = await virtool.db.kinds.verify(db, kind_id, joined=new)

    if issues is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate = virtool.kinds.find_isolate(old["isolates"], isolate_id)

    await virtool.db.history.add(
        db,
        "create_sequence",
        old,
        new,
        "Created new sequence {} in {}".format(data["_id"], virtool.kinds.format_isolate_name(isolate)),
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    headers = {
        "Location": "/api/kinds/{}/isolates/{}/sequences/{}".format(kind_id, isolate_id, data["_id"])
    }

    return json_response(virtool.utils.base_processor(data), status=201, headers=headers)


@validation({
    "host": {"type": "string"},
    "definition": {"type": "string"},
    "segment": {"type": "string"},
    "sequence": {"type": "string"},
    "schema": {"type": "list"}
})
async def edit_sequence(req):
    db, data = req.app["db"], req["data"]

    if not len(data):
        return bad_request("Empty Input")

    kind_id, isolate_id, sequence_id = (req.match_info[key] for key in ["kind_id", "isolate_id", "sequence_id"])

    document = await db.kinds.find_one({"_id": kind_id, "isolates.id": isolate_id})

    if not document:
        return not_found()

    old = await virtool.db.kinds.join(db, kind_id, document)

    segment = data.get("segment", None)

    if segment and segment not in {s["name"] for s in document.get("schema", {})}:
        return not_found("Segment not found")

    updated_sequence = await db.sequences.find_one_and_update({"_id": sequence_id}, {
        "$set": data
    }, return_document=ReturnDocument.AFTER)

    if not updated_sequence:
        return not_found()

    document = await db.kinds.find_one_and_update({"_id": kind_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    }, return_document=ReturnDocument.AFTER)

    new = await virtool.db.kinds.join(db, kind_id, document)

    if await virtool.db.kinds.verify(db, kind_id, joined=new) is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate = virtool.kinds.find_isolate(old["isolates"], isolate_id)

    await virtool.db.history.add(
        db,
        "edit_sequence",
        old,
        new,
        "Edited sequence {} in {}".format(sequence_id, virtool.kinds.format_isolate_name(isolate)),
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    return json_response(virtool.utils.base_processor(updated_sequence))


async def remove_sequence(req):
    """
    Remove a sequence from an isolate.

    """
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]
    isolate_id = req.match_info["isolate_id"]
    sequence_id = req.match_info["sequence_id"]

    if not await db.sequences.count({"_id": sequence_id}):
        return not_found()

    old = await virtool.db.kinds.join(db, kind_id)

    if not old:
        return not_found()

    isolate = virtool.kinds.find_isolate(old["isolates"], isolate_id)

    await db.sequences.delete_one({"_id": sequence_id})

    await db.kinds.update_one({"_id": kind_id}, {
        "$set": {
            "verified": False
        },
        "$inc": {
            "version": 1
        }
    })

    new = await virtool.db.kinds.join(db, kind_id)

    if await virtool.db.kinds.verify(db, kind_id, joined=new) is None:
        await db.kinds.update_one({"_id": kind_id}, {
            "$set": {
                "verified": True
            }
        })

        new["verified"] = True

    isolate_name = virtool.kinds.format_isolate_name(isolate)

    await virtool.db.history.add(
        db,
        "remove_sequence",
        old,
        new,
        "Removed sequence {} from {}".format(sequence_id, isolate_name),
        req["client"].user_id
    )

    await virtool.kinds.dispatch_version_only(req, new)

    return no_content()


async def list_history(req):
    db = req.app["db"]

    kind_id = req.match_info["kind_id"]

    if not await db.kinds.find({"_id": kind_id}).count():
        return not_found()

    documents = await db.history.find({"kind.id": kind_id}).to_list(None)

    return json_response(documents)


async def get_import(req):
    db = req.app["db"]

    file_id = req.query["file_id"]

    file_path = os.path.join(req.app["settings"].get("data_path"), "files", file_id)

    if await db.kinds.count() or await db.indexes.count() or await db.history.count():
        return conflict("Can only import kinds into a virgin instance")

    if not os.path.isfile(file_path):
        return not_found("File not found")

    data = await req.app.loop.run_in_executor(
        req.app["executor"],
        virtool.refs.load_import_file,
        file_path
    )

    isolate_counts = list()
    sequence_counts = list()

    kinds = data["data"]

    for kind in kinds:
        isolates = kind["isolates"]
        isolate_counts.append(len(isolates))

        for isolate in isolates:
            sequence_counts.append(len(isolate["sequences"]))

    duplicates, errors = await req.app.loop.run_in_executor(
        req.app["executor"],
        virtool.refs.validate_kinds,
        data["data"]
    )

    return json_response({
        "file_id": file_id,
        "totals": {
            "kinds": len(kinds),
            "isolates": sum(isolate_counts),
            "sequences": sum(sequence_counts),
        },
        "duplicates": duplicates,
        "version": data["version"],
        "file_created_at": data["created_at"],
        "errors": errors
    })


async def import_kinds(req):
    db, data = await unpack_request(req)

    file_id = data["file_id"]

    file_path = os.path.join(req.app["settings"].get("data_path"), "files", file_id)

    if await db.kinds.count() or await db.indexes.count() or await db.history.count():
        return conflict("Can only import kinds into a virgin instance")

    if not os.path.isfile(file_path):
        return not_found("File not found")

    data = await req.app.loop.run_in_executor(
        req.app["executor"],
        virtool.refs.load_import_file,
        file_path
    )

    data_version = data.get("version", None)

    if not data_version:
        return bad_request("File is not compatible with this version of Virtool")

    asyncio.ensure_future(virtool.db.refs.import_data(
        db,
        req.app["dispatcher"].dispatch,
        data,
        req["client"].user_id
    ), loop=req.app.loop)

    return json_response({}, status=201, headers={"Location": "/api/kinds"})


async def export(req):
    """
    Export all kinds and sequences as a gzipped JSON string. Made available as a downloadable file named
    ``kinds.json.gz``.

    """
    db = req.app["db"]

    # A list of joined kinds.
    kind_list = list()

    async for document in db.kinds.find({"last_indexed_version": {"$ne": None}}):
        # If the kind has been changed since the last index rebuild, patch it to its last indexed version.
        if document["version"] != document["last_indexed_version"]:
            _, joined, _ = await virtool.db.history.patch_to_version(
                db,
                document["_id"],
                document["last_indexed_version"]
            )
        else:
            joined = await virtool.db.kinds.join(db, document["_id"], document)

        kind_list.append(joined)

    # Convert the list of kinds to a JSON-formatted string.
    json_string = json.dumps(kind_list)

    # Compress the JSON string with gzip.
    body = await req.app.loop.run_in_executor(req.app["process_executor"], gzip.compress, bytes(json_string, "utf-8"))

    return web.Response(
        headers={"Content-Disposition": "attachment; filename='kinds.json.gz'"},
        content_type="application/gzip",
        body=body
    )