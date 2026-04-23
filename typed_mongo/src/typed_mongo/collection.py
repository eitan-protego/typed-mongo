"""Type-safe wrapper around pymongo's AsyncCollection.

TypedCollection[M, Model, Path, Query, Fields, Update] provides typed method
signatures that use generated types instead of ``dict[str, Any]``, catching
field path typos and wrong update value types at type-check time.

Type parameters:
    M: MongoCollectionModel subclass
    Model: TypedDict matching ``model_dump()`` output shape
    Path: Literal path type (e.g. ``UserPath``) for single-field args like distinct
    Query: Query TypedDict (e.g. ``UserQuery``) for filter args
    Fields: Fields TypedDict (e.g. ``UserFields``) for $set value args
    Update: Update TypedDict (e.g. ``UserUpdate``) for update documents
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, overload

from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.command_cursor import AsyncCommandCursor
from pymongo.asynchronous.cursor import AsyncCursor
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from typed_mongo.model import MongoCollectionModel
from typed_mongo.operators import AggregationStep

_Direction = Literal[1, -1]


class TypedCursor[M: BaseModel, Path: str]:
    """Typed cursor wrapper that yields validated model instances.

    Wraps an ``AsyncCursor`` and validates each document into model ``M``
    when iterating or calling ``to_list()``.
    """

    def __init__(self, model: type[M], cursor: AsyncCursor[dict[str, Any]]) -> None:
        self._model: type[M] = model
        self._cursor: AsyncCursor[dict[str, Any]] = cursor

    @overload
    def sort(
        self, key_or_list: Path | Sequence[Path], direction: _Direction
    ) -> TypedCursor[M, Path]: ...

    @overload
    def sort(
        self, key_or_list: Sequence[tuple[Path, _Direction]] | Mapping[Path, _Direction]
    ) -> TypedCursor[M, Path]: ...

    def sort(
        self,
        key_or_list: Path
        | Sequence[Path | tuple[Path, _Direction]]
        | Mapping[Path, _Direction],
        direction: _Direction | None = None,
    ) -> TypedCursor[M, Path]:
        if direction is not None:
            self._cursor = self._cursor.sort(key_or_list, direction)  # pyright: ignore[reportArgumentType]
        else:
            self._cursor = self._cursor.sort(key_or_list)  # pyright: ignore[reportArgumentType]
        return self

    def skip(self, count: int) -> TypedCursor[M, Path]:
        self._cursor = self._cursor.skip(count)
        return self

    def limit(self, count: int) -> TypedCursor[M, Path]:
        self._cursor = self._cursor.limit(count)
        return self

    async def to_list(self, length: int | None = None) -> list[M]:
        if length is not None:
            docs = await self._cursor.to_list(length)
        else:
            docs = await self._cursor.to_list()
        return [self._model.model_validate(doc) for doc in docs]

    def __aiter__(self) -> TypedCursor[M, Path]:
        return self

    async def __anext__(self) -> M:
        doc = await self._cursor.__anext__()
        return self._model.model_validate(doc)


class TypedCollection[
    M: MongoCollectionModel,
    Model: Mapping[str, Any],
    Path: str,
    Query: Mapping[str, Any],
    Fields: Mapping[str, Any],
    Update: Mapping[str, Any],
    PipelineStage: Mapping[str, Any],
]:
    """Type-safe wrapper around ``AsyncCollection``.

    Method signatures use generated types instead of ``dict[str, Any]``,
    so that field path typos and wrong update value types are caught at
    type-check time.

    Type parameters:
        M: MongoCollectionModel subclass
        Model: TypedDict matching ``model_dump()`` output shape
        Path: Literal path type (e.g. ``UserPath``) for single-field args
        Query: Query TypedDict (e.g. ``UserQuery``) for filter args
        Fields: Fields TypedDict (e.g. ``UserFields``) for $set value args
        Update: Update TypedDict (e.g. ``UserUpdate``) for update documents
        PipelineStage: Pipeline stage TypedDict union for type-safe aggregation
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
    ) -> TypedCollection[M, Any, Any, Any, Any, Any, Any]:
        """Factory: create a TypedCollection from a database and model class."""
        collection = model.get_collection(db)
        return cls(model, collection)

    # --- Read operations ---

    async def find_one(self, filter: Query) -> M | None:
        """Find a single document matching the filter."""
        doc = await self._collection.find_one(filter)
        if doc is None:
            return None
        return self._model.model_validate(doc)

    def find(self, filter: Query | None = None) -> TypedCursor[M, Path]:
        """Find documents matching the filter."""
        cursor = self._collection.find(filter)
        return TypedCursor(self._model, cursor)

    async def count_documents(self, filter: Query) -> int:
        """Count documents matching the filter."""
        return await self._collection.count_documents(filter)

    async def distinct(self, key: Path, filter: Query | None = None) -> list[Any]:
        """Get distinct values for a field."""
        return await self._collection.distinct(key, filter=filter)

    @overload
    async def aggregate(
        self, pipeline: list[PipelineStage]
    ) -> TypedCursor[M, Path]: ...

    @overload
    async def aggregate(
        self,
        pipeline: list[PipelineStage],
        type_unsafe_pipeline_suffix: list[AggregationStep],
    ) -> AsyncCommandCursor[dict[str, Any]]: ...

    async def aggregate(
        self,
        pipeline: list[PipelineStage],
        type_unsafe_pipeline_suffix: list[AggregationStep] | None = None,
    ) -> TypedCursor[M, Path] | AsyncCommandCursor[dict[str, Any]]:
        """Run an aggregation pipeline.

        With only safe pipeline stages, returns TypedCursor[M] that validates
        results as model instances. With type_unsafe_pipeline_suffix, returns
        a raw AsyncCommandCursor since the output shape is unknown.
        """
        # TypedDicts are dicts at runtime but pyright can't assign TypedDict → dict[str, Any]
        full_pipeline: list[dict[str, Any]] = list(pipeline)  # pyright: ignore[reportAssignmentType]
        if type_unsafe_pipeline_suffix:
            full_pipeline.extend(type_unsafe_pipeline_suffix)  # pyright: ignore[reportArgumentType]
            return await self._collection.aggregate(full_pipeline)
        cursor: Any = await self._collection.aggregate(full_pipeline)
        return TypedCursor(self._model, cursor)

    # --- Write operations ---

    async def insert_one(self, document: M | Model) -> InsertOneResult:
        """Insert a document (model instance or dict)."""
        # Model TypedDict is a dict at runtime; pyright can't narrow M | Model through ternary
        doc: dict[str, Any] = (
            document.model_dump() if isinstance(document, BaseModel) else document
        )  # pyright: ignore[reportAssignmentType]
        return await self._collection.insert_one(doc)

    async def replace_one(
        self,
        filter: Query,
        replacement: M | Model,
        upsert: bool = False,
    ) -> UpdateResult:
        """Replace a document (model instance or dict)."""
        # Model TypedDict is a dict at runtime; pyright can't narrow M | Model through ternary
        doc: dict[str, Any] = (
            replacement.model_dump()
            if isinstance(replacement, BaseModel)
            else replacement
        )  # pyright: ignore[reportAssignmentType]
        return await self._collection.replace_one(filter, doc, upsert=upsert)

    async def update_one(
        self,
        filter: Query,
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
        filter: Query,
        update: Update,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """Type-safe update of multiple documents."""
        return await self._collection.update_many(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def delete_one(self, filter: Query) -> DeleteResult:
        """Delete a single document matching the filter."""
        return await self._collection.delete_one(filter)

    # --- Escape hatch ---

    @property
    def raw(self) -> AsyncCollection[dict[str, Any]]:
        """Access the underlying ``AsyncCollection`` directly."""
        return self._collection
