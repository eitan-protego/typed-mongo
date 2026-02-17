"""Type-safe wrapper around pymongo's AsyncCollection.

TypedCollection[M, P, Q, F] provides typed method signatures that use
generated types instead of ``dict[str, Any]``, catching field path typos
and wrong ``$set`` value types at type-check time.

Type parameters:
    M: MongoCollectionModel subclass
    P: Literal path type (e.g. ``UserPath``) for single-field args like distinct
    Q: Query TypedDict (e.g. ``UserQuery``) for filter args
    F: Fields TypedDict (e.g. ``UserFields``) for $set value args
"""

from __future__ import annotations

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

    def __init__(self, model: type[M], cursor: AsyncCursor) -> None:  # type: ignore[type-arg]
        self._model = model
        self._cursor = cursor

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


class TypedCollection[M: MongoCollectionModel, P, Q, F]:
    """Type-safe wrapper around ``AsyncCollection``.

    Method signatures use generated types (M, P, Q, F) instead of
    ``dict[str, Any]``, so that field path typos and wrong ``$set``
    value types are caught at type-check time.

    Usage::

        from typed_mongo import MongoCollectionModel
        from my_app.types import UserCollection

        class User(MongoCollectionModel):
            __collection_name__ = "users"
            name: str
            email: str

        users = UserCollection(db)

        # Type-checked filter and field values:
        await users.find_one({"name": "Alice"})
        await users.set_fields({"name": "Alice"}, {"email": "alice@example.com"})
    """

    def __init__(
        self,
        model: type[M],
        collection: AsyncCollection,  # type: ignore[type-arg]
    ) -> None:
        self._model = model
        self._collection = collection

    @classmethod
    def from_database(
        cls, model: type[M], db: AsyncDatabase[dict[str, Any]]
    ) -> TypedCollection[M, Any, Any, Any]:
        """Factory: create a TypedCollection from a database and model class."""
        collection = model.get_collection(db)
        return cls(model, collection)

    # --- Read operations ---

    async def find_one(self, filter: Q) -> M | None:  # noqa: A002
        """Find a single document matching the filter.

        Returns a validated model instance, or ``None`` if not found.
        """
        doc = await self._collection.find_one(filter)
        if doc is None:
            return None
        return self._model.model_validate(doc)

    def find(self, filter: Q | None = None) -> TypedCursor[M]:  # noqa: A002
        """Find documents matching the filter.

        Returns a ``TypedCursor`` that validates each document.
        """
        cursor = self._collection.find(filter)
        return TypedCursor(self._model, cursor)

    async def count_documents(self, filter: Q) -> int:  # noqa: A002
        """Count documents matching the filter."""
        return await self._collection.count_documents(filter)  # type: ignore[arg-type]

    async def distinct(  # noqa: A002
        self, key: P, filter: Q | None = None
    ) -> list[Any]:
        """Get distinct values for a field.

        Args:
            key: Field path (type-checked against the Literal path type).
            filter: Optional query filter.
        """
        return await self._collection.distinct(key, filter=filter)  # type: ignore[arg-type]

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> list[M]:
        """Run an aggregation pipeline and validate results as models."""
        cursor = await self._collection.aggregate(pipeline)
        docs = await cursor.to_list()
        return [self._model.model_validate(doc) for doc in docs]

    # --- Write operations ---

    async def insert_one(self, document: M) -> InsertOneResult:
        """Insert a document, serialized via ``model_dump()``.

        Note: Uses ``model_dump()`` (NOT ``model_dump(by_alias=True)``).
        If your model uses aliases, ensure serialize_by_alias is set in
        model_config.
        """
        doc = document.model_dump()
        return await self._collection.insert_one(doc)

    async def replace_one(
        self,
        filter: Q,
        replacement: M,
        upsert: bool = False,
    ) -> UpdateResult:
        """Replace a document, serialized via ``model_dump()``.

        Note: Uses ``model_dump()`` (NOT ``model_dump(by_alias=True)``).
        If your model uses aliases, ensure serialize_by_alias is set in
        model_config.
        """
        doc = replacement.model_dump()
        return await self._collection.replace_one(filter, doc, upsert=upsert)

    async def update_one(
        self,
        filter: Q,  # noqa: A002
        update: dict[str, Any],
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """General update passthrough.

        For type-safe ``$set`` operations, prefer ``set_fields()`` instead.
        """
        return await self._collection.update_one(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def set_fields(
        self,
        filter: Q,
        fields: F,
        upsert: bool = False,
    ) -> UpdateResult:
        """Type-safe ``$set`` update using the Fields TypedDict.

        Wraps *fields* in ``{"$set": fields}`` and delegates to the
        underlying collection's ``update_one``.
        """
        return await self._collection.update_one(
            filter, {"$set": fields}, upsert=upsert
        )

    async def delete_one(self, filter: Q) -> DeleteResult:  # noqa: A002
        """Delete a single document matching the filter."""
        return await self._collection.delete_one(filter)

    # --- Escape hatch ---

    @property
    def raw(self) -> AsyncCollection:  # type: ignore[type-arg]
        """Access the underlying ``AsyncCollection`` directly.

        Use this when you need operations not covered by TypedCollection.
        """
        return self._collection
