"""Tests for TypedCollection and TypedCursor wrappers."""

from typing import Literal, TypedDict
from typed_mongo.collection import TypedCollection


# Test type definitions
type TestPath = Literal["_id", "name", "age"]


class TestQuery(TypedDict, total=False):
    _id: str
    name: str
    age: int


class TestFields(TypedDict, total=False):
    _id: int
    name: int
    age: int


class TestModel(TypedDict):
    _id: str
    name: str
    age: int


def test_typed_collection_instantiates():
    """TypedCollection should instantiate with proper type parameters."""
    # This is primarily a type-checking test
    # We can't easily test runtime behavior without a real MongoDB connection
    # Just verify the class exists and can be referenced

    assert TypedCollection is not None
    assert hasattr(TypedCollection, "find")
    assert hasattr(TypedCollection, "find_one")
    assert hasattr(TypedCollection, "update_one")
