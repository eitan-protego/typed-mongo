"""Tests for code generation."""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from typed_mongo_gen.codegen import write_field_paths


class _TestModel(BaseModel):
    model_config = {"alias_generator": to_camel}
    id: str = Field(validation_alias="_id", serialization_alias="_id")
    name: str
    age: int | None = None


def test_write_field_paths_creates_both_files(tmp_path):
    """write_field_paths should create both .py and .pyi files."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    assert runtime_path.exists()
    assert stub_path.exists()


def test_runtime_file_has_simple_aliases(tmp_path):
    """Runtime .py file should have simple type aliases."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = runtime_path.read_text()
    assert "from typing import Any" in content
    assert "type TestModelPath = str" in content
    assert "TestModelQuery = dict[str, Any]" in content
    assert "TestModelFields = dict[str, Any]" in content
    # Should NOT have full types
    assert "Literal[" not in content
    assert "TypedDict(" not in content


def test_stub_file_has_full_types(tmp_path):
    """Stub .pyi file should have full Literal and TypedDict types."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    assert "type TestModelPath = Literal[" in content
    assert '"_id",' in content
    assert '"name",' in content
    assert '"age",' in content
    assert 'TestModelQuery = TypedDict("TestModelQuery"' in content
    assert '"_id": Op[str],' in content
    assert '"age": Op[int | None],' in content


def test_stub_file_includes_fields_typed_dict(tmp_path):
    """Stub .pyi file should include Fields TypedDict with exact types."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    assert 'TestModelFields = TypedDict("TestModelFields"' in content
    assert '"_id": str,' in content
    assert '"name": str,' in content
    assert '"age": int | None,' in content


def test_generated_code_compiles(tmp_path):
    """Generated stub file should be valid Python."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")
