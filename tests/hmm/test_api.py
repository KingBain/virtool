import json
import shutil

import aiofiles
import aiohttp
import pytest
import virtool.errors
from aiohttp.test_utils import make_mocked_coro
from virtool.utils import decompress_file


async def test_find(mocker, snapshot, spawn_client, hmm_document):
    """
    Check that a request with no URL parameters returns a list of HMM annotation documents.

    """
    m = mocker.patch("virtool.hmm.db.get_status", make_mocked_coro({"id": "hmm"}))

    client = await spawn_client(authorize=True)

    hmm_document["hidden"] = False

    await client.db.hmm.insert_one(hmm_document)

    resp = await client.get("/hmms")

    assert resp.status == 200
    assert await resp.json() == snapshot

    m.assert_called_with(client.db)


async def test_get_status(mocker, spawn_client):
    client = await spawn_client(authorize=True)

    mocker.patch(
        "virtool.hmm.db.get_status", make_mocked_coro({"id": "hmm", "updating": True})
    )

    resp = await client.get("/hmms/status")

    assert resp.status == 200

    assert await resp.json() == {"id": "hmm", "updating": True}


@pytest.mark.parametrize("error", [None, "502_repo", "502_github", "404"])
async def test_get_release(error, mocker, spawn_client, resp_is):
    """
    Test that the endpoint returns the latest HMM release. Check that error responses are sent in all expected
    situations.

    """
    client = await spawn_client(authorize=True)

    m_fetch = make_mocked_coro(
        None if error == "404" else {"name": "v2.0.1", "newer": False}
    )

    mocker.patch("virtool.hmm.db.fetch_and_update_release", new=m_fetch)

    if error == "502_repo":
        m_fetch.side_effect = virtool.errors.GitHubError("404 Not found")

    if error == "502_github":
        m_fetch.side_effect = aiohttp.ClientConnectorError("foo", OSError("Bar"))

    resp = await client.get("/hmms/status/release")

    m_fetch.assert_called_with(client.app)

    if error == "404":
        await resp_is.not_found(resp, "Release not found")
        return

    if error == "502_repo":
        await resp_is.bad_gateway(resp, "GitHub repository does not exist")
        return

    if error == "502_github":
        await resp_is.bad_gateway(resp, "Could not reach GitHub")
        return

    assert resp.status == 200
    assert await resp.json() == {"name": "v2.0.1", "newer": False}


@pytest.mark.parametrize("error", [None, "404"])
async def test_get(error, spawn_client, hmm_document, resp_is):
    """
    Check that a ``GET`` request for a valid annotation document results in a response containing that complete
    document.

    Check that a `404` is returned if the HMM does not exist.

    """
    client = await spawn_client(authorize=True)

    if not error:
        await client.db.hmm.insert_one(hmm_document)

    resp = await client.get("/hmms/f8666902")

    if error:
        await resp_is.not_found(resp)
        return

    assert resp.status == 200

    expected = dict(hmm_document, id=hmm_document["_id"])
    expected.pop("_id")

    assert await resp.json() == expected


async def test_get_hmm_annotations(spawn_job_client, tmp_path):
    client = await spawn_job_client(authorize=True)
    client.app["config"].data_path = tmp_path
    db = client.app["db"]

    await db.hmm.insert_one({"_id": "foo"})
    await db.hmm.insert_one({"_id": "bar"})

    compressed_hmm_annotations = tmp_path / "annotations.json.gz"
    decompressed_hmm_annotations = tmp_path / "annotations.json"

    async with client.get("/hmms/files/annotations.json.gz") as response:
        assert response.status == 200

        async with aiofiles.open(compressed_hmm_annotations, "wb") as f:
            await f.write(await response.read())

        decompress_file(compressed_hmm_annotations, decompressed_hmm_annotations)

        async with aiofiles.open(decompressed_hmm_annotations, "r") as f:
            hmms = json.loads(await f.read())

        assert hmms == [{"id": "foo"}, {"id": "bar"}]


@pytest.mark.parametrize("data_exists", [True, False])
@pytest.mark.parametrize("file_exists", [True, False])
async def test_get_hmm_profiles(
    data_exists,
    file_exists,
    snapshot,
    example_path,
    spawn_client,
    spawn_job_client,
    tmp_path,
):
    """
    Test that HMM profiles can be properly downloaded once they are available.

    """
    client = await spawn_job_client(authorize=True)

    client.app["config"].data_path = tmp_path
    hmms_path = tmp_path / "hmm"
    profiles_path = hmms_path / "profiles.hmm"

    if data_exists:
        hmms_path.mkdir()

        if file_exists:
            shutil.copy(example_path / "hmms" / "profiles.hmm", hmms_path)
            assert profiles_path.exists()

    resp = await client.get("/hmms/files/profiles.hmm")

    if data_exists and file_exists:
        assert resp.status == 200
        assert profiles_path.read_bytes() == await resp.content.read()
    else:
        assert resp.status == 404
