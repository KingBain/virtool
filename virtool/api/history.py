import virtool.db.history
import virtool.errors
import virtool.history
import virtool.kinds
import virtool.utils
from virtool.api.utils import conflict, json_response, no_content, not_found, paginate


async def find(req):
    """
    Get a list of change documents.

    """
    db = req.app["db"]

    data = await paginate(
        db.history,
        {},
        req.query,
        sort="created_at",
        projection=virtool.db.history.LIST_PROJECTION,
        reverse=True
    )

    return json_response(data)


async def get(req):
    """
    Get a specific change document by its ``change_id``.

    """
    db = req.app["db"]

    change_id = req.match_info["change_id"]

    document = await db.history.find_one(change_id, virtool.db.history.PROJECTION)

    if not document:
        return not_found()

    return json_response(virtool.utils.base_processor(document))


async def revert(req):
    """
    Remove the change document with the given ``change_id`` and any subsequent changes.

    """
    db = req.app["db"]

    change_id = req.match_info["change_id"]

    try:
        await virtool.db.history.revert(db, change_id)
    except virtool.errors.DatabaseError as err:
        err_string = str(err)

        if "Change does not exist" in err_string:
            return not_found()

        if "Change is already built" in err_string:
            return conflict("Change is already built")

    return no_content()