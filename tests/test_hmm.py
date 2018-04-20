import gzip
import json
import operator
import os
import pytest
import shutil
import sys
from aiohttp import web
from aiohttp.test_utils import make_mocked_coro

import virtool.hmm

TEST_FILE_PATH = os.path.join(sys.path[0], "tests", "test_files")


@pytest.fixture
def mock_gh_server(monkeypatch, loop, test_server):
    async def get_handler(req):
        data = {
            "assets": [
                {
                    "id": 5265064,
                    "name": "annotations.json.gz",
                    "content_type": "application/gzip",
                    "state": "uploaded",
                    "size": 792158,
                    "download_count": 0,
                    "created_at": "2017-11-06T20:56:09Z",
                    "updated_at": "2017-11-06T20:56:12Z",
                    "browser_download_url": "https://github.com/virtool/virtool-hmm/releases/download/v0.1.0/annotation"
                                            "s.json.gz"
                },
                {
                    "id": 5263449,
                    "name": "profiles.hmm.gz",
                    "content_type": "application/gzip",
                    "state": "uploaded",
                    "size": 85106197,
                    "download_count": 0,
                    "created_at": "2017-11-06T18:45:13Z",
                    "updated_at": "2017-11-06T18:49:29Z",
                    "browser_download_url": "https://github.com/virtool/virtool-hmm/releases/download/v0.1.0/profiles.h"
                                            "mm.gz"
                }
            ]
        }

        return web.json_response(data)

    app = web.Application()

    app.router.add_get("/latest", get_handler)

    server = loop.run_until_complete(test_server(app))

    monkeypatch.setattr("virtool.hmm.LATEST_RELEASE_URL", "http://{}:{}/latest".format(server.host, server.port))

    return server


@pytest.mark.parametrize("step", [False, None, "decompress_profiles"])
async def test_update_process(step, mocker):
    m = mocker.patch("virtool.utils.update_status_process", new=make_mocked_coro())

    if step is False:
        await virtool.hmm.update_process("db", "dispatch", 0.65)
    else:
        await virtool.hmm.update_process("db", "dispatch", 0.65, step=step)

    assert m.call_args[0] == ("db", "dispatch", "hmm_install", 0.65, step or None)


async def test_get_assets(mocker):
    # This data doesn"t represent a complete response from the GitHub API. It is reduced for brevity.
    m = make_mocked_coro({
        "assets": [
            {
                "id": 5265064,
                "name": "annotations.json.gz",
                "content_type": "application/gzip",
                "state": "uploaded",
                "size": 792158,
                "download_count": 0,
                "created_at": "2017-11-06T20:56:09Z",
                "updated_at": "2017-11-06T20:56:12Z",
                "browser_download_url": "https://github.com/virtool/virtool-hmm/releases/download/v0.1.0/annotation"
                                        "s.json.gz"
            }
        ]
    })

    mocker.patch("virtool.github.get", new=m)

    assets = await virtool.hmm.get_asset({"proxy_enable": False}, "v1.9.2-beta.2", "fred", "abc123")

    assert assets == [(
        "https://github.com/virtool/virtool-hmm/releases/download/v0.1.0/annotations.json.gz",
        792158
    )]


async def test_install_official(loop, mocker, tmpdir, test_motor, test_dispatch):
    tmpdir.mkdir("hmm")

    settings = {
        "proxy_enable": False,
        "data_path": str(tmpdir)
    }

    m_get_assets = make_mocked_coro([(
        "https://github.com/virtool/virtool-hmm/releases/download/v0.1.0/annotations.json.gz",
        792158
    )])

    m_download_asset = mocker.stub(name="download_asset")

    async def download_asset(settings, url, size, target_path, progress_handler):
        m_download_asset(settings, url, size, target_path, progress_handler)
        shutil.copyfile(os.path.join(TEST_FILE_PATH, "vthmm.tar.gz"), os.path.join(target_path))

    m_update_process = make_mocked_coro()

    mocker.patch("virtool.hmm.get_asset", new=m_get_assets)
    mocker.patch("virtool.hmm.update_process", new=m_update_process)
    mocker.patch("virtool.github.download_asset", new=download_asset)

    await virtool.hmm.install_official(
        loop,
        test_motor,
        settings,
        test_dispatch,
        "v1.9.2-beta.2"
    )

    m_get_assets.assert_called_with(settings, "v1.9.2-beta.2", None, None)


async def test_insert_annotations(test_motor, test_random_alphanumeric):
    with gzip.open(os.path.join(TEST_FILE_PATH, "annotations.json.gz"), "rt") as f:
        annotations = json.load(f)

    await virtool.hmm.insert_annotations(test_motor, annotations)

    expected_ids = {"9pfsom1b", "g5cpjjvk", "kfvw9vd2", "u3cuwaoq", "v4xryery", "xjqvxigh", "yglirxr7"}

    assert set(await test_motor.hmm.distinct("_id")) == expected_ids

    annotations = sorted(annotations, key=operator.itemgetter("cluster"))

    assert await test_motor.hmm.find({}, sort=[("cluster", 1)]).to_list(None) == annotations