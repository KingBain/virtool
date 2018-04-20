from cerberus import Validator
from pymongo import ReturnDocument

import virtool.db.account
import virtool.db.users
import virtool.db.utils
import virtool.users
import virtool.utils
import virtool.validators
from virtool.api.utils import bad_request, invalid_input, json_response, no_content, not_found, protected, validation

API_KEY_PROJECTION = {
    "_id": False,
    "user": False
}

SETTINGS_SCHEMA = {
    "show_ids": {
        "type": "boolean",
        "required": False
    },
    "skip_quick_analyze_dialog": {
        "type": "boolean",
        "required": False
    },
    "quick_analyze_algorithm": {
        "type": "string",
        "required": False
    }
}


@protected()
async def get(req):
    """
    Get complete user document

    """
    user_id = req["client"].user_id

    document = await req.app["db"].users.find_one(user_id, virtool.db.users.ACCOUNT_PROJECTION)

    return json_response(virtool.utils.base_processor(document))


@protected()
async def edit(req):
    """
    Edit the user account.

    """
    db = req.app["db"]
    data = await req.json()
    user_id = req["client"].user_id

    minlength = req.app["settings"]["minimum_password_length"]

    v = Validator({
        "email": {"type": "string", "regex": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"},
        "old_password": {"type": "string", "minlength": minlength},
        "password": {"type": "string", "minlength": minlength, "dependencies": "old_password"}
    })

    if not v.validate(data):
        return invalid_input(v.errors)

    data = v.document

    try:
        update = await virtool.db.account.compose_password_update(
            db,
            user_id,
            data["old_password"],
            data["password"]
        )
    except ValueError as err:
        if "Invalid credentials" in str(err):
            return bad_request("Invalid credentials")
        raise

    if "email" in data:
        update["email"] = data["email"]

    document = await db.users.find_one_and_update({"_id": user_id}, {
        "$set": update
    }, return_document=ReturnDocument.AFTER, projection=virtool.db.users.ACCOUNT_PROJECTION)

    return json_response(virtool.utils.base_processor(document))


@protected()
async def get_settings(req):
    """
    Get account settings

    """
    user_id = req["client"].user_id

    document = await req.app["db"].users.find_one(user_id)

    return json_response(document["settings"])


@protected()
@validation(SETTINGS_SCHEMA)
async def update_settings(req):
    """
    Update account settings.

    """
    db, data = req.app["db"], req["data"]

    user_id = req["client"].user_id

    document = await db.users.find_one(user_id, ["settings"])

    settings = {
        **document["settings"],
        **data
    }

    await db.users.update_one({"_id": user_id}, {
        "$set": settings
    })

    return json_response(settings)


@protected()
async def get_api_keys(req):
    db = req.app["db"]

    user_id = req["client"].user_id

    api_keys = await db.keys.find({"user.id": user_id}, API_KEY_PROJECTION).to_list(None)

    return json_response(api_keys, status=200)


@protected()
async def get_api_key(req):
    db = req.app["db"]
    user_id = req["client"].user_id
    key_id = req.match_info.get("key_id")

    document = await db.keys.find_one({"id": key_id, "user.id": user_id}, API_KEY_PROJECTION)

    if document is None:
        return not_found()

    return json_response(document, status=200)


@protected()
@validation({
    "name": {"type": "string", "required": True, "minlength": 1},
    "permissions": {"type": "dict", "validator": virtool.validators.is_permission_dict}
})
async def create_api_key(req):
    """
    Create a new API key.

    """
    db = req.app["db"]
    data = req["data"]

    user_id = req["client"].user_id

    name = data["name"]

    permissions = {
        **{p: False for p in virtool.users.PERMISSIONS},
        **data.get("permissions", {})
    }

    raw, hashed = virtool.db.account.get_api_key()

    document = {
        "_id": hashed,
        "id": await virtool.db.account.get_alternate_id(db, name),
        "name": name,
        "groups": req["client"].groups,
        "permissions": permissions,
        "created_at": virtool.utils.timestamp(),
        "user": {
            "id": user_id
        }
    }

    await db.keys.insert_one(document)

    del document["_id"]
    del document["user"]

    document["key"] = raw

    headers = {
        "Location": "/api/account/keys/{}".format(document["id"])
    }

    return json_response(document, headers=headers, status=201)


@protected()
@validation({
    "permissions": {"type": "dict", "validator": virtool.validators.is_permission_dict}
})
async def update_api_key(req):
    db = req.app["db"]
    data = req["data"]

    key_id = req.match_info.get("key_id")

    user_id = req["client"].user_id

    permissions = await virtool.db.utils.get_one_field(db.keys, "permissions", {"id": key_id, "user.id": user_id})

    if permissions is None:
        return not_found()

    permissions.update(data["permissions"])

    document = await db.keys.find_one_and_update({"id": key_id}, {
        "$set": {
            "permissions": permissions
        }
    }, return_document=ReturnDocument.AFTER, projection={"_id": False, "user": False})

    return json_response(document)


@protected()
async def remove_api_key(req):
    db = req.app["db"]

    user_id = req["client"].user_id
    key_id = req.match_info.get("key_id")

    delete_result = await db.keys.delete_one({"id": key_id, "user.id": user_id})

    if delete_result.deleted_count == 0:
        return not_found()

    return no_content()


@protected()
async def remove_all_api_keys(req):
    db = req.app["db"]

    await db.keys.delete_many({"user.id": req["client"].user_id})

    return no_content()


@protected()
async def logout(req):
    """
    Invalidates the requesting session, effectively logging out the user.

    """
    db = req.app["db"]

    session_id = req["client"].session_id

    if session_id:
        await db.sessions.delete_one({"_id": session_id})

    return no_content()