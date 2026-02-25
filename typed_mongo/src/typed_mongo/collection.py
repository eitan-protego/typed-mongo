"""Type-safe wrapper around pymongo's AsyncCollection.

TypedCollection[M, Path, Query, Fields, Update] provides typed method
signatures that use generated types instead of ``dict[str, Any]``, catching
field path typos and wrong update value types at type-check time.

Type parameters:
    M: MongoCollectionModel subclass
    Path: Literal path type (e.g. ``UserPath``) for single-field args like distinct
    Query: Query TypedDict (e.g. ``UserQuery``) for filter args
    Fields: Fields TypedDict (e.g. ``UserFields``) for $set value args
    Update: Update TypedDict (e.g. ``UserUpdate``) for update documents
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.cursor import AsyncCursor
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from typed_mongo.model import MongoCollectionModel


class TypedCursor[M: BaseModel]:
    """Typed cursor wrapper that yields validated model instances.

    Wraps an ``AsyncCursor`` and validates each document into model ``M``
    when iterating or calling ``to_list()``.
    """

    def __init__(self, model: type[M], cursor: AsyncCursor[dict[str, Any]]) -> None:
        self._model: type[M] = model
        self._cursor: AsyncCursor[dict[str, Any]] = cursor

    def sort(self, *args: Any, **kwargs: Any) -> TypedCursor[M]:
        """Sort results. Returns self for chaining."""
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, count: int) -> TypedCursor[M]:
        """Skip results. Returns self for chaining."""
        self._cursor = self._cursor.skip(count)
        return self

    def limit(self, count: int) -> TypedCursor[M]:
        """Limit results. Returns self for chaining."""
        self._cursor = self._cursor.limit(count)
        return self

    async def to_list(self, length: int | None = None) -> list[M]:
        """Fetch all documents and validate each into model M."""
        if length is not None:
            docs = await self._cursor.to_list(length)
        else:
            docs = await self._cursor.to_list()
        return [self._model.model_validate(doc) for doc in docs]

    def __aiter__(self) -> TypedCursor[M]:
        return self

    async def __anext__(self) -> M:
        doc = await self._cursor.__anext__()
        return self._model.model_validate(doc)


class TypedCollection[
    M: MongoCollectionModel,
    Path: str,
    Query: Mapping[str, Any],
    Fields: Mapping[str, Any],
    Update: Mapping[str, Any],
]:
    """Type-safe wrapper around ``AsyncCollection``.

    Method signatures use generated types (M, Path, Query, Fields, Update)
    instead of ``dict[str, Any]``, so that field path typos and wrong
    update value types are caught at type-check time.

    Type parameters:
        M: MongoCollectionModel subclass
        Path: Literal path type (e.g. ``UserPath``) for single-field args
        Query: Query TypedDict (e.g. ``UserQuery``) for filter args
        Fields: Fields TypedDict (e.g. ``UserFields``) for $set value args
        Update: Update TypedDict (e.g. ``UserUpdate``) for update documents
    """

    def __init__(
        self,
        model: type[M],
        collection: AsyncCollection[dict[str, Any]],
    ) -> None:
        self._model: type[M] = model
        self._collection: AsyncCollection[dict[str, Any]] = collection

    @classmethod
    def from_database(
        cls, model: type[M], db: AsyncDatabase[dict[str, Any]]
    ) -> TypedCollection[M, Any, Any, Any, Any]:
        """Factory: create a TypedCollection from a database and model class."""
        collection = model.get_collection(db)
        return cls(model, collection)

    # --- Read operations ---

    async def find_one(self, filter: Query) -> M | None:  # noqa: A002
        """Find a single document matching the filter."""
        doc = await self._collection.find_one(filter)
        if doc is None:
            return None
        return self._model.model_validate(doc)

    def find(self, filter: Query | None = None) -> TypedCursor[M]:  # noqa: A002
        """Find documents matching the filter."""
        cursor = self._collection.find(filter)
        return TypedCursor(self._model, cursor)

    async def count_documents(self, filter: Query) -> int:  # noqa: A002
        """Count documents matching the filter."""
        return await self._collection.count_documents(filter)

    async def distinct(  # noqa: A002
        self, key: Path, filter: Query | None = None
    ) -> list[Any]:
        """Get distinct values for a field."""
        return await self._collection.distinct(key, filter=filter)

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> list[M]:
        """Run an aggregation pipeline and validate results as models."""
        cursor = await self._collection.aggregate(pipeline)
        docs = await cursor.to_list()
        return [self._model.model_validate(doc) for doc in docs]

    # --- Write operations ---

    async def insert_one(self, document: M) -> InsertOneResult:
        """Insert a document, serialized via ``model_dump()``."""
        doc = document.model_dump()
        return await self._collection.insert_one(doc)

    async def replace_one(
        self,
        filter: Query,
        replacement: M,
        upsert: bool = False,
    ) -> UpdateResult:
        """Replace a document, serialized via ``model_dump()``."""
        doc = replacement.model_dump()
        return await self._collection.replace_one(filter, doc, upsert=upsert)

    async def update_one(
        self,
        filter: Query,  # noqa: A002
        update: Update,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """Type-safe update of a single document."""
        return await self._collection.update_one(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def update_many(
        self,
        filter: Query,  # noqa: A002
        update: Update,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """Type-safe update of multiple documents."""
        return await self._collection.update_many(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def delete_one(self, filter: Query) -> DeleteResult:  # noqa: A002
        """Delete a single document matching the filter."""
        return await self._collection.delete_one(filter)

    # --- Escape hatch ---

    @property
    def raw(self) -> AsyncCollection[dict[str, Any]]:
        """Access the underlying ``AsyncCollection`` directly."""
        return self._collection
