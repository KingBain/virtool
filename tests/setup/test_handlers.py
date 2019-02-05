import pytest


async def test_unavailable(spawn_client):
    client = await spawn_client(setup=True)

    resp = await client.get("/api/otus")

    assert resp.status == 503

    assert await resp.json() == {
        "id": "requires_setup",
        "message": "Server is not configured"
    }

    assert resp.headers["Location"] == "/setup"


@pytest.mark.parametrize("error", (None, "auth_error", "connection_error", "name_error"))
@pytest.mark.parametrize("ready", (True, False))
@pytest.mark.parametrize("populated", (True, False))
async def test_get_db(error, populated, ready, mocker, snapshot, spawn_client, setup_defaults):
    """
    Test that the HTML is rendered correctly given that db setup state.

    """
    client = await spawn_client(setup=True)

    if populated:
        client.app["setup"]["db"].update({
            "db_connection_string": "mongodb://www.example.com:27017",
            "db_name": "foo",
            "error": error,
            "ready": ready
        })

    resp = await client.get("/setup/db")

    assert resp.status == 200

    snapshot.assert_match(await resp.text())


@pytest.mark.parametrize("path", ("data", "watch"))
@pytest.mark.parametrize("populated", (True, False))
@pytest.mark.parametrize("ready", (True, False))
@pytest.mark.parametrize("value", ("", "foo", "/foo/bar"))
async def test_get_paths(path, populated, ready, value, snapshot, spawn_client):
    client = await spawn_client(setup=True)

    if populated:
        client.app["setup"][path].update({
            "path": value,
            "ready": ready
        })

    resp = await client.get(f"/setup/{path}")

    assert resp.status == 200

    snapshot.assert_match(await resp.text())


async def test_post_user(mocker, spawn_client, setup_defaults):
    client = await spawn_client(setup=True)

    update = {
        "id": "baz",
        "password": "foobar",
        "password_confirm": "foobar"
    }

    mocker.patch("virtool.users.hash_password", return_value="hashed")

    assert client.app["setup"] == setup_defaults

    resp = await client.post_form("/setup/user", update)

    assert client.app["setup"] == {
        **setup_defaults,
        "user": {
            "id": "baz",
            "password": "hashed",
            "placeholder": "******",
            "error": None,
            "ready": True
        }
    }

    assert resp.status == 200
