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
