"""Tests for code generation."""

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typed_mongo_gen.codegen import write_field_paths


class _TestModel(BaseModel):
    id: str = Field(validation_alias="_id", serialization_alias="_id")
    name: str
    age: int | None = None

    model_config: ClassVar[ConfigDict] = {"alias_generator": to_camel}


def test_write_field_paths_creates_both_files(tmp_path: Path):
    """write_field_paths should create both .py and .pyi files."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    assert runtime_path.exists()
    assert stub_path.exists()


def test_runtime_file_has_simple_aliases(tmp_path: Path):
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


def test_stub_file_has_full_types(tmp_path: Path):
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


def test_stub_file_includes_fields_typed_dict(tmp_path: Path):
    """Stub .pyi file should include Fields TypedDict with exact types."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    assert 'TestModelFields = TypedDict("TestModelFields"' in content
    assert '"_id": str,' in content
    assert '"name": str,' in content
    assert '"age": int | None,' in content


def test_query_has_logical_operators(tmp_path: Path):
    """Query TypedDict should have $and, $or, $nor, $not with recursive typing."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    assert '"$and": list["TestModelQuery"],' in content
    assert '"$or": list["TestModelQuery"],' in content
    assert '"$nor": list["TestModelQuery"],' in content
    assert '"$not": "TestModelQuery",' in content


def test_generated_code_compiles(tmp_path: Path):
    """Generated stub file should be valid Python."""
    runtime_path = tmp_path / "test_types.py"
    stub_path = tmp_path / "test_types.pyi"

    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")


def test_list_field_query_type_is_op_element_or_list(tmp_path: Path):
    """Query TypedDict for list[T] fields should use Op[T | list[T]]."""

    class _ModelWithList(BaseModel):
        tags: list[str]
        ids: list[int]

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"ModelWithList": _ModelWithList})

    content = stub_path.read_text()
    assert '"tags": Op[str | list[str]],' in content
    assert '"ids": Op[int | list[int]],' in content


def test_nested_list_field_query_type_includes_all_levels(tmp_path: Path):
    """Query TypedDict for list[list[list[T]]] should use Op[T | list[T] | list[list[T]] | list[list[list[T]]]]."""

    class _ModelWithNestedList(BaseModel):
        matrix: list[list[list[str]]]

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(
        runtime_path, stub_path, {"ModelWithNestedList": _ModelWithNestedList}
    )

    content = stub_path.read_text()
    expected = (
        '"matrix": Op[str | list[str] | list[list[str]] | list[list[list[str]]]],'
    )
    assert expected in content


def test_union_with_list_expands_list_member(tmp_path: Path):
    """Query TypedDict for list[Foo] | None and list[Foo] | str should expand list to Op[Foo | list[Foo]] and keep union."""

    class _ModelWithOptionalList(BaseModel):
        tags: list[str] | None
        ids: list[int] | str

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(
        runtime_path, stub_path, {"ModelWithOptionalList": _ModelWithOptionalList}
    )

    content = stub_path.read_text()
    assert '"tags": Op[str | list[str] | None],' in content
    assert '"ids": Op[int | list[int] | str],' in content


class _ModelWithMixedFields(BaseModel):
    name: str
    age: int | None = None
    score: float = 0.0
    tags: list[str] = []
    active: bool = True


def test_numeric_fields_typed_dict(tmp_path: Path):
    """Stub should have NumericFields with only int/float fields."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedNumericFields = TypedDict("MixedNumericFields"' in content
    # Extract the NumericFields section
    start = content.index("MixedNumericFields = TypedDict(")
    numeric_section = content[start:content.index("total=False)", start) + len("total=False)")]
    assert '"age": int | float,' in numeric_section
    assert '"score": int | float,' in numeric_section
    # name, tags, active should NOT be in NumericFields
    assert '"name"' not in numeric_section
    assert '"tags"' not in numeric_section
    assert '"active"' not in numeric_section


def test_array_element_fields_typed_dict(tmp_path: Path):
    """Stub should have ArrayElementFields with only list fields, mapped to element type."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedArrayElementFields = TypedDict("MixedArrayElementFields"' in content
    # Extract the section between the assignment and the closing total=False)
    start = content.index("MixedArrayElementFields = TypedDict(")
    array_section = content[start:content.index("total=False)", start) + len("total=False)")]
    assert '"tags": str,' in array_section


def test_array_pop_fields_typed_dict(tmp_path: Path):
    """Stub should have ArrayPopFields with list fields mapped to Literal[1, -1]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedArrayPopFields = TypedDict("MixedArrayPopFields"' in content
    start = content.index("MixedArrayPopFields = TypedDict(")
    pop_section = content[start:content.index("total=False)", start) + len("total=False)")]
    assert '"tags": Literal[1, -1],' in pop_section


def test_unset_fields_typed_dict(tmp_path: Path):
    """Stub should have UnsetFields with all fields mapped to Literal['']."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedUnsetFields = TypedDict("MixedUnsetFields"' in content
    start = content.index("MixedUnsetFields = TypedDict(")
    unset_section = content[start:content.index("total=False)", start) + len("total=False)")]
    assert "\"name\": Literal['']," in unset_section
    assert "\"age\": Literal['']," in unset_section
    assert "\"score\": Literal['']," in unset_section
    assert "\"tags\": Literal['']," in unset_section


def test_runtime_has_new_type_aliases(tmp_path: Path):
    """Runtime .py should have dict[str, Any] aliases for new types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert "MixedNumericFields = dict[str, Any]" in content
    assert "MixedArrayElementFields = dict[str, Any]" in content
    assert "MixedArrayPopFields = dict[str, Any]" in content
    assert "MixedUnsetFields = dict[str, Any]" in content


def test_ref_path_literal_type(tmp_path: Path):
    """Stub should have RefPath with $-prefixed field paths."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedRefPath = Literal[" in content
    assert '"$name",' in content
    assert '"$age",' in content
    assert '"$score",' in content
    assert '"$tags",' in content


def test_update_typed_dict(tmp_path: Path):
    """Stub should have Update TypedDict with all operator keys."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedUpdate = TypedDict("MixedUpdate"' in content
    # Find the Update section
    update_start = content.index('MixedUpdate = TypedDict("MixedUpdate"')
    update_end = content.index("total=False)", update_start)
    update_section = content[update_start:update_end]
    assert '"$set": MixedFields,' in update_section
    assert '"$unset": MixedUnsetFields,' in update_section
    assert '"$inc": MixedNumericFields,' in update_section
    assert '"$mul": MixedNumericFields,' in update_section
    assert '"$min": MixedFields,' in update_section
    assert '"$max": MixedFields,' in update_section
    assert '"$push": MixedArrayElementFields,' in update_section
    assert '"$pull": MixedArrayElementFields,' in update_section
    assert '"$addToSet": MixedArrayElementFields,' in update_section
    assert '"$pop": MixedArrayPopFields,' in update_section


def test_pipeline_set_fields_typed_dict(tmp_path: Path):
    """Stub should have PipelineSetFields with T | RefPath | Mapping[AggExprOp, Any]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedPipelineSetFields = TypedDict("MixedPipelineSetFields"' in content
    ps_start = content.index('MixedPipelineSetFields = TypedDict(')
    ps_end = content.index("total=False)", ps_start)
    ps_section = content[ps_start:ps_end]
    assert '"name": str | MixedRefPath | Mapping[AggExprOp, Any],' in ps_section
    assert '"score": float | MixedRefPath | Mapping[AggExprOp, Any],' in ps_section


def test_pipeline_stage_union(tmp_path: Path):
    """Stub should have PipelineStage union type."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineStage = MixedPipelineSet | MixedPipelineUnset" in content
    assert 'MixedPipelineSet = TypedDict("MixedPipelineSet"' in content
    assert 'MixedPipelineUnset = TypedDict("MixedPipelineUnset"' in content


def test_collection_stub_has_six_type_params(tmp_path: Path):
    """Generated Collection stub should use all 6 type params including Model and Update."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    expected = "TypedCollection[_ModelWithMixedFields, MixedModel, MixedPath, MixedQuery, MixedFields, MixedUpdate]"
    assert expected in content


def test_model_typed_dict(tmp_path: Path):
    """Stub should have Model TypedDict with top-level fields only."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedModel = TypedDict("MixedModel"' in content
    model_start = content.index('MixedModel = TypedDict("MixedModel"')
    model_end = content.index("})", model_start)
    model_section = content[model_start:model_end]
    assert '"name": str,' in model_section
    assert '"age": int | None,' in model_section
    assert '"score": float,' in model_section
    assert '"tags": list[str],' in model_section
    assert '"active": bool,' in model_section
    # Should NOT have total=False (model_dump returns all fields)
    assert "total=False" not in content[model_start:model_end + 10]


def test_generated_update_code_compiles(tmp_path: Path):
    """Generated stub with all update types should compile."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")
