from cerberus import Validator
from settings import SCHEMA
from handlers.utils import unpack_json_request, json_response, not_found, invalid_input


async def get_all(req):
    return json_response(req.app["settings"].data)


async def get_one(req):
    key = req.match_info["key"]

    if key not in SCHEMA:
        return not_found("Unknown setting key")

    return json_response(req["settings"].data[key])


async def update(req):
    """
    Update application settings based on request data.
    
    """
    db, data = await unpack_json_request(req)

    settings = req.app["settings"]

    v = Validator(SCHEMA)

    if not v.validate(data):
        return invalid_input(v.errors)

    document = v.document

    settings.data.update(document)

    await settings.write_to_file

    return json_response(req["settings"].data)
