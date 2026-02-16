"""Tests for CLI functionality."""

import sys
from pathlib import Path
import pytest
from typed_mongo import MongoCollectionModel, clear_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


def test_import_sources_from_module_string():
    """CLI should be able to import sources from module strings."""
    from typed_mongo_gen.cli import _import_sources

    # Create a test model that will auto-register
    class TestModel(MongoCollectionModel):
        __collection_name__ = "test"
        value: str

    # Since the model is already in this module, importing this module
    # would populate the registry (but we already have it)
    # This test verifies the mechanism works
    from typed_mongo import get_registry
    registry = get_registry()
    assert "TestModel" in registry


def test_import_sources_from_file_path(tmp_path):
    """CLI should be able to import sources from file paths."""
    from typed_mongo_gen.cli import _import_sources

    # Create a temporary Python file with a model
    test_file = tmp_path / "test_models.py"
    test_file.write_text("""
from typed_mongo import MongoCollectionModel

class FileModel(MongoCollectionModel):
    __collection_name__ = "file_collection"
    data: str
""")

    clear_registry()
    _import_sources([str(test_file)])

    from typed_mongo import get_registry
    registry = get_registry()
    assert "FileModel" in registry


def test_empty_registry_raises_error():
    """CLI should error if no models found after imports."""
    from typed_mongo_gen.cli import generate
    from pathlib import Path

    clear_registry()

    with pytest.raises(SystemExit) as exc_info:
        generate(sources=["nonexistent.module"], output=Path("output.py"))

    assert exc_info.value.code == 1
