from logging import getLogger

from pymongo.errors import DuplicateKeyError

import virtool.db.mongo
from virtool.analyses.migrate import migrate_analyses
from virtool.caches.migrate import migrate_caches
from virtool.groups.migrate import migrate_groups
from virtool.references.migrate import migrate_references
from virtool.samples.migrate import migrate_samples
from virtool.types import App

logger = getLogger(__name__)


async def migrate(app: App):
    """
    Update all collections on application start.

    Used for applying MongoDB schema and file storage changes.

    :param app: the application object

    """
    funcs = (
        migrate_analyses,
        migrate_caches,
        migrate_groups,
        migrate_sessions,
        migrate_status,
        migrate_samples,
        migrate_references,
    )

    for func in funcs:
        name = func.__name__.replace("migrate_", "")
        logger.info(f" • {name}")
        await func(app)


async def migrate_sessions(app: App):
    """
    Add the expiry index to the sessions collection.

    :param app: the application object

    """
    await app["db"].sessions.create_index("expiresAt", expireAfterSeconds=0)


async def migrate_status(app: App):
    """
    Automatically update the status collection.

    :param app: the application object

    """
    db = app["db"]
    server_version = app["version"]

    await db.status.delete_many({"_id": {"$in": ["software_update", "version"]}})

    mongo_version = await virtool.db.mongo.get_mongo_version(db)

    await db.status.update_many({}, {"$unset": {"process": ""}})

    try:
        await db.status.insert_one(
            {
                "_id": "software",
                "installed": None,
                "mongo_version": mongo_version,
                "releases": list(),
                "task": None,
                "updating": False,
                "version": server_version,
            }
        )
    except DuplicateKeyError:
        await db.status.update_one(
            {"_id": "software"},
            {
                "$set": {
                    "mongo_version": mongo_version,
                    "task": None,
                    "updating": False,
                    "version": server_version,
                }
            },
        )

    try:
        await db.status.insert_one(
            {
                "_id": "hmm",
                "installed": None,
                "task": None,
                "updates": list(),
                "release": None,
            }
        )
    except DuplicateKeyError:
        if await db.hmm.count_documents({}):
            await db.status.update_one(
                {"_id": "hmm", "installed": {"$exists": False}},
                {"$set": {"installed": None}},
            )
