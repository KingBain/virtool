import pytest

import virtool.db.indexes
import virtool.errors
import virtool.jobs.build_index


async def test_create_manifest(test_motor, test_kind):
    await test_motor.kinds.insert_many([
        test_kind,
        dict(test_kind, _id="foo", version=5),
        dict(test_kind, _id="baz", version=3, ref={"id": "123"}),
        dict(test_kind, _id="bar", version=11)
    ])

    assert await virtool.db.indexes.create_manifest(test_motor, "hxn167") == {
        "6116cba1": 0,
        "foo": 5,
        "bar": 11
    }


@pytest.mark.parametrize("exists", [True, False])
@pytest.mark.parametrize("has_ref", [True, False])
async def test_get_current_id_and_version(exists, has_ref, test_indexes, test_motor):
    if not exists:
        test_indexes = [dict(i, ready=False, has_files=False) for i in test_indexes]

    await test_motor.indexes.insert_many(test_indexes)

    ref_id = "hxn167" if has_ref else "foobar"

    index_id, index_version = await virtool.db.indexes.get_current_id_and_version(test_motor, ref_id)

    if has_ref and exists:
        assert index_id == "ptlrcefm"
        assert index_version == 3

    else:
        assert index_id is None
        assert index_version == -1


@pytest.mark.parametrize("value", ["jgwlhulj", 2])
@pytest.mark.parametrize("projection", (
    None,
    ["_id", "version"]
))
async def test_get_index(projection, value, test_indexes, test_motor):
    await test_motor.indexes.insert_many(test_indexes)

    expected = test_indexes[2]

    if projection:
        expected = {k: expected[k] for k in projection}

    assert await virtool.db.indexes.get_index(test_motor, value, projection) == expected


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("has_ref", [True, False])
async def test_get_next_version(empty, has_ref, test_indexes, test_motor):
    if not empty:
        await test_motor.indexes.insert_many(test_indexes)

    expected = 4

    if empty or not has_ref:
        expected = 0

    assert await virtool.db.indexes.get_next_version(test_motor, "hxn167" if has_ref else "foobar") == expected


async def test_tag_unbuilt_changes(test_motor, create_mock_history):
    await create_mock_history(False)

    async for document in test_motor.history.find():
        await test_motor.history.insert({
            **document,
            "_id": "foo_" + document["_id"],
            "ref": {
                "id": "foobar"
            }
        })

    assert await test_motor.history.count({"index.id": "unbuilt"}) == 8
    assert await test_motor.history.count({"ref.id": "foobar", "index.id": "unbuilt"}) == 4
    assert await test_motor.history.count({"ref.id": "hxn167", "index.id": "unbuilt"}) == 4

    await virtool.db.indexes.tag_unbuilt_changes(test_motor, "hxn167", "foo", 5)

    assert await test_motor.history.count({"ref.id": "foobar", "index.id": "unbuilt"}) == 4
    assert await test_motor.history.count({"ref.id": "hxn167", "index.id": "foo", "index.version": 5}) == 4