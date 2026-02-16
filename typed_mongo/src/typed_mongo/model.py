"""MongoDB collection model base class with automatic registry."""

from typing import ClassVar, Any
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection


# Module-level registry
_MODEL_REGISTRY: dict[str, type["MongoCollectionModel"]] = {}


def get_registry() -> dict[str, type["MongoCollectionModel"]]:
    """Return a copy of the current model registry.

    Returns:
        Dictionary mapping model class names to MongoCollectionModel subclasses
    """
    return _MODEL_REGISTRY.copy()


def clear_registry() -> None:
    """Clear the model registry.

    Useful for testing to ensure clean state between tests.
    """
    _MODEL_REGISTRY.clear()


class MongoCollectionModel(BaseModel):
    """Base class for MongoDB collection models with automatic registry.

    Subclasses that define __collection_name__ are automatically registered
    when the class is defined. The registry is used by the typed_mongo_gen
    package to discover models for code generation.

    Example:
        class User(MongoCollectionModel):
            __collection_name__ = "users"

            name: str
            email: str
    """

    __collection_name__: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        """Register concrete models when subclass is defined."""
        super().__init_subclass__(**kwargs)
        # Only register models that have __collection_name__ defined
        # This allows abstract base classes to inherit without registering
        if "__collection_name__" in cls.__dict__:
            _MODEL_REGISTRY[cls.__name__] = cls

    @classmethod
    def get_collection(
        cls, db: AsyncIOMotorDatabase
    ) -> AsyncIOMotorCollection[dict[str, Any]]:
        """Get the MongoDB collection for this model.

        Args:
            db: Motor AsyncIOMotorDatabase instance

        Returns:
            AsyncIOMotorCollection for this model's collection
        """
        return db.get_collection(cls.__collection_name__)
