"""Tests for CLI functionality."""

from pathlib import Path
from textwrap import dedent

import pytest
from typed_mongo_gen.cli import _collect_models, _expand_sources


_MODEL_SOURCE = dedent("""\
    from typed_mongo import MongoCollectionModel

    class FileModel(MongoCollectionModel):
        __collection_name__ = "file_collection"
        data: str
""")


def test_collect_models_from_file(tmp_path: Path):
    """_collect_models should find MongoCollectionModel subclasses via runpy."""
    test_file = tmp_path / "models.py"
    test_file.write_text(_MODEL_SOURCE)

    models = _collect_models([test_file])
    assert "FileModel" in models
    assert models["FileModel"].__collection_name__ == "file_collection"


def test_collect_models_skips_abstract(tmp_path: Path):
    """_collect_models should skip classes without __collection_name__ in __dict__."""
    test_file = tmp_path / "models.py"
    test_file.write_text(dedent("""\
        from typed_mongo import MongoCollectionModel

        class AbstractBase(MongoCollectionModel):
            data: str

        class Concrete(MongoCollectionModel):
            __collection_name__ = "things"
            data: str
    """))

    models = _collect_models([test_file])
    assert "AbstractBase" not in models
    assert "Concrete" in models


def test_expand_sources_glob(tmp_path: Path):
    """_expand_sources should expand glob patterns."""
    sub = tmp_path / "models"
    sub.mkdir()
    (sub / "a.py").write_text("# a")
    (sub / "b.py").write_text("# b")
    (sub / "c.txt").write_text("# c")

    paths = _expand_sources([str(sub / "*.py")], exclude=set())
    assert len(paths) == 2
    names = {p.name for p in paths}
    assert names == {"a.py", "b.py"}


def test_expand_sources_excludes_output(tmp_path: Path):
    """_expand_sources should exclude specified paths."""
    (tmp_path / "models.py").write_text("# models")
    (tmp_path / "_generated_types.py").write_text("# generated")

    exclude = {(tmp_path / "_generated_types.py").resolve()}
    paths = _expand_sources([str(tmp_path / "*.py")], exclude=exclude)
    names = {p.name for p in paths}
    assert "_generated_types.py" not in names
    assert "models.py" in names


def test_expand_sources_recursive_glob(tmp_path: Path):
    """_expand_sources should support ** recursive globs."""
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    (tmp_path / "top.py").write_text("# top")
    (sub / "deep.py").write_text("# deep")

    paths = _expand_sources([str(tmp_path / "**" / "*.py")], exclude=set())
    names = {p.name for p in paths}
    assert "top.py" in names
    assert "deep.py" in names


def test_expand_sources_no_match_errors(tmp_path: Path):
    """_expand_sources should exit if a pattern matches nothing."""
    with pytest.raises(SystemExit):
        _expand_sources([str(tmp_path / "nonexistent_*.py")], exclude=set())
