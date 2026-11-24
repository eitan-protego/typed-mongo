import asyncio
from typing import Any, ClassVar, cast
from unittest.mock import AsyncMock

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from typed_mongo.collection import TypedCollection
from typed_mongo.model import MongoCollectionModel


class SampleModel(MongoCollectionModel):
    __collection_name__: ClassVar[str] = "tests"
    value: str


def test_transaction_operations_forward_session() -> None:
    async def run() -> None:
        raw = AsyncMock()
        raw.find_one.return_value = None
        collection: TypedCollection[
            SampleModel,
            dict[str, Any],
            str,
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ] = TypedCollection(
            SampleModel,
            cast(AsyncCollection[dict[str, Any]], raw),
        )
        session = cast(AsyncClientSession, object())

        await collection.find_one({}, session=session)
        await collection.insert_one(SampleModel(value="value"), session=session)
        await collection.update_one({}, {"$set": {"value": "updated"}}, session=session)
        await collection.delete_one({}, session=session)

        assert raw.find_one.call_args.kwargs["session"] is session
        assert raw.insert_one.call_args.kwargs["session"] is session
        assert raw.update_one.call_args.kwargs["session"] is session
        assert raw.delete_one.call_args.kwargs["session"] is session

    asyncio.run(run())


def test_find_one_sort() -> None:
    async def run() -> None:
        raw = AsyncMock()

        async def find_one(filter: dict[str, Any], *, sort: Any, session: Any) -> Any:
            assert session is marker
            docs = [
                doc
                for doc in [{"value": "a"}, {"value": "b"}]
                if all(doc.get(k) == v for k, v in filter.items())
            ]
            return (
                sorted(docs, key=lambda doc: doc[sort[0][0]], reverse=sort[0][1] == -1)[
                    0
                ]
                if docs
                else None
            )

        raw.find_one.side_effect = find_one
        collection: TypedCollection[
            SampleModel,
            dict[str, Any],
            str,
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ] = TypedCollection(SampleModel, cast(AsyncCollection[dict[str, Any]], raw))
        marker = cast(AsyncClientSession, object())
        assert await collection.find_one(
            {}, sort=[("value", -1)], session=marker
        ) == SampleModel(value="b")
        assert (
            await collection.find_one(
                {"value": "missing"}, sort=[("value", 1)], session=marker
            )
            is None
        )

    asyncio.run(run())


def test_with_options_preserves_model_validation() -> None:
    from unittest.mock import patch

    import pytest
    from pydantic import ValidationError
    from pymongo import AsyncMongoClient, ReadPreference
    from typed_mongo.collection import TypedCursor

    async def run() -> None:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(connect=False)
        original = TypedCollection[
            SampleModel,
            dict[str, Any],
            str,
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ](SampleModel, client.test.tests)
        configured = original.with_options(read_preference=ReadPreference.NEAREST)
        assert configured is not original
        assert configured.raw.read_preference == ReadPreference.NEAREST
        assert original.raw.read_preference == ReadPreference.PRIMARY
        assert configured.with_options().raw.read_preference == ReadPreference.NEAREST
        assert configured.raw.full_name == original.raw.full_name
        assert configured.raw.database.client is client

        raw_cursor = AsyncMock()
        raw_cursor.to_list.return_value = [{"value": "valid"}]
        pipeline = [{"$match": {"value": "valid"}}]
        with patch.object(
            AsyncCollection, "aggregate", new_callable=AsyncMock
        ) as aggregate:
            aggregate.return_value = raw_cursor
            cursor = await configured.aggregate(pipeline)
            assert isinstance(cursor, TypedCursor)
            assert await cursor.to_list() == [SampleModel(value="valid")]
            aggregate.assert_awaited_once_with(pipeline)
            raw_cursor.to_list.return_value = [{"value": {}}]
            with pytest.raises(ValidationError):
                await cursor.to_list()
        await client.close()

    asyncio.run(run())


def test_find_one_and_update_validates_and_forwards_options() -> None:
    import pytest
    from pydantic import Field, ValidationError
    from pymongo import ReturnDocument

    class AliasedModel(SampleModel):
        value: str = Field(alias="storedValue")

    async def run() -> None:
        raw = AsyncMock()
        collection = TypedCollection[
            AliasedModel,
            dict[str, Any],
            str,
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ](AliasedModel, cast(AsyncCollection[dict[str, Any]], raw))
        query = {"storedValue": "before"}
        update = {"$set": {"storedValue": "after"}}
        raw.find_one_and_update.return_value = {"storedValue": "before"}
        assert await collection.find_one_and_update(query, update) == AliasedModel(
            storedValue="before"
        )
        assert (
            raw.find_one_and_update.call_args.kwargs["return_document"]
            == ReturnDocument.BEFORE
        )

        pipeline = [{"$set": {"storedValue": {"$concat": ["$storedValue", "!"]}}}]
        session = cast(AsyncClientSession, object())
        raw.find_one_and_update.return_value = {"storedValue": "after"}
        assert await collection.find_one_and_update(
            query,
            pipeline,
            return_document=ReturnDocument.AFTER,
            upsert=True,
            sort=[("storedValue", -1)],
            array_filters=[{"x": 1}],
            session=session,
            hint="value_index",
            let={"suffix": "!"},
            collation={"locale": "en"},
            maxTimeMS=1000,
        ) == AliasedModel(storedValue="after")
        raw.find_one_and_update.assert_awaited_with(
            query,
            pipeline,
            return_document=ReturnDocument.AFTER,
            upsert=True,
            sort=[("storedValue", -1)],
            array_filters=[{"x": 1}],
            session=session,
            hint="value_index",
            let={"suffix": "!"},
            collation={"locale": "en"},
            maxTimeMS=1000,
        )
        raw.find_one_and_update.return_value = None
        assert await collection.find_one_and_update(query, update) is None
        raw.find_one_and_update.return_value = {"storedValue": {}}
        with pytest.raises(ValidationError):
            await collection.find_one_and_update(query, update)
        raw.find_one_and_update.side_effect = RuntimeError("database failed")
        with pytest.raises(RuntimeError, match="database failed"):
            await collection.find_one_and_update(query, update)
        raw.find_one.assert_not_awaited()

        await collection.update_one(query, pipeline)
        assert raw.update_one.call_args.args == (query, pipeline)
        await collection.update_many(query, pipeline)
        assert raw.update_many.call_args.args == (query, pipeline)

    asyncio.run(run())
