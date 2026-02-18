"""Tests for MongoCollectionModel registry."""

from typing import ClassVar

import pytest
from typed_mongo.model import MongoCollectionModel, clear_registry, get_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


def test_subclass_auto_registers():
    """Subclassing MongoCollectionModel should auto-register the model."""
    clear_registry()

    class TestModel(MongoCollectionModel):
        __collection_name__: ClassVar[str] = "test_collection"
        name: str

    registry = get_registry()
    assert "TestModel" in registry
    assert registry["TestModel"] is TestModel


def test_multiple_models_all_register():
    """Multiple models should all register independently."""
    clear_registry()

    class ModelA(MongoCollectionModel):
        __collection_name__: ClassVar[str] = "collection_a"
        field_a: str

    class ModelB(MongoCollectionModel):
        __collection_name__: ClassVar[str] = "collection_b"
        field_b: int

    registry = get_registry()
    assert ModelA.__name__ in registry
    assert ModelB.__name__ in registry
    assert len(registry) == 2


def test_get_registry_returns_copy():
    """get_registry should return a copy, not the internal dict."""

    class TestModel(MongoCollectionModel):  # pyright: ignore[reportUnusedClass]
        __collection_name__: ClassVar[str] = "test"
        value: str

    registry1 = get_registry()
    registry2 = get_registry()

    assert registry1 == registry2
    assert registry1 is not registry2  # Different dict instances


def test_clear_registry_removes_all():
    """clear_registry should remove all registered models."""

    class TestModel(MongoCollectionModel):  # pyright: ignore[reportUnusedClass]
        __collection_name__: ClassVar[str] = "test"
        data: str

    assert len(get_registry()) > 0
    clear_registry()
    assert len(get_registry()) == 0


def test_model_without_collection_name_not_registered():
    """Abstract base models without __collection_name__ should not register."""
    clear_registry()

    class AbstractBase(MongoCollectionModel):
        common_field: str

    # Should not be in registry since no __collection_name__
    registry = get_registry()
    assert AbstractBase.__name__ not in registry
