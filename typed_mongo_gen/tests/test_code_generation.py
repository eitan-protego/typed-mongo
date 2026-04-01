"""Tests for code generation."""

import io
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typed_mongo_gen.codegen import write_typeddict, write_field_paths
from typed_mongo_gen.introspect import has_default


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
    # _id, name, age are all valid identifiers -> class syntax
    assert "class TestModelFields(TypedDict, total=False):" in content
    assert "    _id: str" in content
    assert "    name: str" in content
    assert "    age: int | None" in content


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


def test_numeric_fields_type_alias(tmp_path: Path):
    """Stub should have NumericFields as dict[Literal[...], int | float]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedNumericFields = dict[Literal[" in content
    assert "int | float]" in content
    assert '"age"' in content
    assert '"score"' in content


def test_array_fields_type_aliases(tmp_path: Path):
    """Stub should have ArrayPath literal and dict-based array field types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedArrayPath = Literal[" in content
    assert '"tags"' in content
    assert "type MixedArrayElementFields = dict[MixedArrayPath, Any]" in content
    assert "type MixedArrayPushFields = dict[MixedArrayPath, Any]" in content
    assert "type MixedArrayPopFields = dict[MixedArrayPath, Literal[1, -1]]" in content


def test_unset_fields_typed_dict(tmp_path: Path):
    """Stub should have UnsetFields as dict[OptionalPath, Literal[""]]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'type MixedUnsetFields = dict[MixedOptionalPath, Literal[""]]' in content


def test_runtime_has_new_type_aliases(tmp_path: Path):
    """Runtime .py should have dict[str, Any] aliases for new types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert "MixedNumericFields" in content
    assert "MixedArrayPath" in content
    assert "MixedArrayElementFields" in content
    assert "MixedArrayPopFields" in content
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
    """Stub should have Update TypedDict with all operator keys (function-call syntax due to $ keys)."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # $ keys -> function-call syntax
    assert 'MixedUpdate = TypedDict("MixedUpdate"' in content
    update_start = content.index('MixedUpdate = TypedDict("MixedUpdate"')
    update_end = content.index("total=False)", update_start)
    update_section = content[update_start:update_end]
    assert '"$set": MixedFields,' in update_section
    assert '"$setOnInsert": MixedFields,' in update_section
    assert '"$unset": MixedUnsetFields,' in update_section
    assert '"$inc": MixedNumericFields,' in update_section
    assert '"$mul": MixedNumericFields,' in update_section
    assert '"$min": MixedFields,' in update_section
    assert '"$max": MixedFields,' in update_section
    assert '"$push": MixedArrayPushFields,' in update_section
    assert '"$pull": MixedArrayElementFields,' in update_section
    assert '"$addToSet": MixedArrayPushFields,' in update_section
    assert '"$pop": MixedArrayPopFields,' in update_section


def test_pipeline_set_fields_type_alias(tmp_path: Path):
    """Stub should have PipelineSetFields as dict[Path, Any]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineSetFields = dict[MixedPath, Any]" in content


def test_pipeline_stage_union(tmp_path: Path):
    """Stub should have PipelineStage union with all safe stages."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineStage = (" in content
    assert "MixedMatchStage" in content
    assert "MixedSortStage" in content


def test_collection_stub_has_seven_type_params(tmp_path: Path):
    """Generated Collection stub should use all 7 type params including PipelineStage."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    expected = "TypedCollection[_ModelWithMixedFields, MixedDict, MixedPath, MixedQuery, MixedFields, MixedUpdate, MixedPipelineStage]"
    assert expected in content


def test_model_typed_dict(tmp_path: Path):
    """Stub should have Model TypedDict with top-level fields only."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # All keys are valid identifiers, total=True -> class syntax without total kwarg
    assert "class MixedDict(TypedDict):" in content
    model_start = content.index("class MixedDict(TypedDict):")
    model_end = content.index("\n\n", model_start)
    model_section = content[model_start:model_end]
    assert "    name: str" in model_section
    assert "    age: int | None" in model_section
    assert "    score: float" in model_section
    assert "    tags: list[str]" in model_section
    assert "    active: bool" in model_section
    # Should NOT have total=False (model_dump returns all fields)
    assert "total=False" not in model_section


def test_class_syntax_vs_function_call_syntax(tmp_path: Path):
    """TypedDicts with valid identifier keys use class syntax; others use function-call."""

    class _Nested(BaseModel):
        x: int

    class _Parent(BaseModel):
        name: str
        child: _Nested

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Parent": _Parent})

    content = stub_path.read_text()
    # Model has only top-level fields (name, child) -> class syntax
    assert "class ParentDict(TypedDict):" in content
    # Fields has dot-path keys (child.x) -> function-call syntax
    assert 'ParentFields = TypedDict("ParentFields"' in content
    # Query always has $ keys -> function-call syntax
    assert 'ParentQuery = TypedDict("ParentQuery"' in content
    # Update always has $ keys -> function-call syntax
    assert 'ParentUpdate = TypedDict("ParentUpdate"' in content


def test_nested_model_generates_dict_typeddict(tmp_path: Path):
    """Nested BaseModel fields should generate Dict TypedDicts instead of importing the class."""

    class _Address(BaseModel):
        street: str
        city: str

    class _Person(BaseModel):
        name: str
        address: _Address

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Person": _Person})

    content = stub_path.read_text()
    # Should generate _AddressDict TypedDict
    assert "class _AddressDict(TypedDict):" in content
    assert "    street: str" in content
    assert "    city: str" in content
    # PersonDict should reference _AddressDict, not _Address
    assert "address: _AddressDict" in content
    # _Address is still imported (for typed_dump overloads), but not used in field types
    assert "address: _Address\n" not in content


def test_nested_model_in_list_generates_dict(tmp_path: Path):
    """list[Model] fields should use the generated Dict type."""

    class _Tag(BaseModel):
        label: str

    class _Item(BaseModel):
        tags: list[_Tag]

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Item": _Item})

    content = stub_path.read_text()
    assert "class _TagDict(TypedDict):" in content
    assert "tags: list[_TagDict]" in content


def test_nested_model_in_optional_generates_dict(tmp_path: Path):
    """Optional[Model] fields should use the generated Dict type."""

    class _Meta(BaseModel):
        key: str

    class _Doc(BaseModel):
        meta: _Meta | None = None

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Doc": _Doc})

    content = stub_path.read_text()
    assert "class _MetaDict(TypedDict):" in content
    assert "meta: _MetaDict | None" in content


def test_transitive_nested_models(tmp_path: Path):
    """Transitively nested models should all get Dict TypedDicts in dependency order."""

    class _Inner(BaseModel):
        value: int

    class _Middle(BaseModel):
        inner: _Inner

    class _Outer(BaseModel):
        middle: _Middle

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Outer": _Outer})

    content = stub_path.read_text()
    # Both nested models should have Dict TypedDicts
    assert "class _InnerDict(TypedDict):" in content
    assert "class _MiddleDict(TypedDict):" in content
    # _MiddleDict should reference _InnerDict
    assert "inner: _InnerDict" in content
    # _OuterDict should reference _MiddleDict
    assert "middle: _MiddleDict" in content
    # _InnerDict should come before _MiddleDict (dependency order)
    inner_pos = content.index("_InnerDict")
    middle_pos = content.index("_MiddleDict")
    assert inner_pos < middle_pos
    # Should compile
    compile(content, "<test>", "exec")


def test_typed_dump_runtime(tmp_path: Path):
    """Runtime .py should have typed_dump function."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert "def typed_dump(model: BaseModel) -> dict[str, Any]:" in content
    assert "return model.model_dump()" in content


def test_typed_dump_stub_overloads(tmp_path: Path):
    """Stub .pyi should have @overload signatures for typed_dump."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert (
        "@overload\ndef typed_dump(model: _ModelWithMixedFields) -> MixedDict: ..."
        in content
    )


def test_typed_dump_with_nested_models(tmp_path: Path):
    """typed_dump should have overloads for nested models too."""

    class _Inner(BaseModel):
        x: int

    class _Outer(BaseModel):
        child: _Inner

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Outer": _Outer})

    content = stub_path.read_text()
    # Overload for the top-level model
    assert "@overload\ndef typed_dump(model: _Outer) -> OuterDict: ..." in content
    # Overload for the nested model
    assert "@overload\ndef typed_dump(model: _Inner) -> _InnerDict: ..." in content


def test_typed_dump_subclass_before_parent(tmp_path: Path):
    """typed_dump overloads should list subclasses before parents to avoid shadowing."""

    class _Parent(BaseModel):
        x: int

    class _Child(_Parent):
        y: str

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Parent": _Parent, "Child": _Child})

    content = stub_path.read_text()
    child_pos = content.index("def typed_dump(model: _Child)")
    parent_pos = content.index("def typed_dump(model: _Parent)")
    assert child_pos < parent_pos, "Subclass overload must come before parent overload"


def test_generated_update_code_compiles(tmp_path: Path):
    """Generated stub with all update types should compile."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")


# --- Task 3: write_typeddict PEP 728 ---


def testwrite_typeddict_function_call_syntax():
    """write_typeddict should use function-call syntax for non-identifier keys."""
    f = io.StringIO()
    write_typeddict(f, "TestStage", [("$match", "dict[str, Any]")])
    content = f.getvalue()
    assert 'TestStage = TypedDict("TestStage"' in content


# --- Task 4: stub header imports ---


def test_stub_header_imports_typing(tmp_path: Path):
    """Stub should import TypedDict, NotRequired, Required from typing."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    typing_line = [
        line for line in content.splitlines() if line.startswith("from typing import")
    ][0]
    assert "TypedDict" in typing_line
    assert "NotRequired" in typing_line
    assert "Required" in typing_line
    assert "typing_extensions" not in content
    assert "from typed_mongo.operators import AggExprOp, AggregationStep, Op" in content


# --- Task 5: has_default ---


def test_has_default_with_default_value():
    """Fields with default values should return True."""

    class _Model(BaseModel):
        required_field: str
        optional_field: str = "default"
        none_field: int | None = None
        factory_field: list[str] = Field(default_factory=list)

    assert not has_default(_Model, "required_field")
    assert has_default(_Model, "optional_field")
    assert has_default(_Model, "none_field")
    assert has_default(_Model, "factory_field")


# --- Task 6: RefPaths ---


def test_pipeline_set_fields_is_dict_alias(tmp_path: Path):
    """PipelineSetFields should be a simple dict[Path, Any] type alias."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineSetFields = dict[MixedPath, Any]" in content
    # No per-type refs
    assert "MixedStrRefPath" not in content
    assert "MixedFloatRefPath" not in content


# --- Deduplication ---


class _NestedA(BaseModel):
    shared: str = ""
    only_a: int = 0


class _NestedB(BaseModel):
    shared: str = ""
    only_b: float = 0.0


class _ModelWithUnionNested(BaseModel):
    name: str
    nested: _NestedA | _NestedB


def test_optional_path_no_duplicates(tmp_path: Path):
    """OptionalPath should not contain duplicate entries from union variants."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Dup": _ModelWithUnionNested})

    content = stub_path.read_text()
    assert "type DupOptionalPath = Literal[" in content
    opt_start = content.index("type DupOptionalPath = Literal[")
    opt_end = content.index("]", opt_start) + 1
    opt_section = content[opt_start:opt_end]
    # "nested.shared" should appear exactly once despite being in both _NestedA and _NestedB
    assert opt_section.count('"nested.shared"') == 1


def test_all_literal_types_deduplicated(tmp_path: Path):
    """All Literal type aliases should have no duplicate entries."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Dup": _ModelWithUnionNested})

    content = stub_path.read_text()
    # Check every Literal[...] block for duplicates
    import re

    for m in re.finditer(r"type \w+ = Literal\[\n(.*?)\]", content, re.DOTALL):
        entries = re.findall(r'"([^"]+)"', m.group(1))
        assert len(entries) == len(set(entries)), f"Duplicate entries in: {m.group(0)}"


# --- Task 7: OptionalPath and safe stages ---


def test_optional_path_literal(tmp_path: Path):
    """Stub should have OptionalPath with only fields that have defaults."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedOptionalPath = Literal[" in content
    opt_start = content.index("type MixedOptionalPath = Literal[")
    opt_end = content.index("]", opt_start) + 1
    opt_section = content[opt_start:opt_end]
    assert '"age"' in opt_section
    assert '"score"' in opt_section
    assert '"tags"' in opt_section
    assert '"active"' in opt_section
    assert '"name"' not in opt_section


def test_safe_aggregation_stages(tmp_path: Path):
    """Stub should have safe aggregation stage TypedDicts."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedMatchStage = TypedDict("MixedMatchStage"' in content
    assert '"$match": MixedQuery,' in content
    assert 'MixedSortStage = TypedDict("MixedSortStage"' in content
    assert '"$sort": dict[MixedPath, Literal[1, -1]],' in content
    assert 'MixedLimitStage = TypedDict("MixedLimitStage"' in content
    assert '"$limit": int,' in content
    assert 'MixedSkipStage = TypedDict("MixedSkipStage"' in content
    assert '"$skip": int,' in content
    assert 'MixedSetStage = TypedDict("MixedSetStage"' in content
    assert '"$set": MixedPipelineSetFields,' in content
    assert 'MixedAddFieldsStage = TypedDict("MixedAddFieldsStage"' in content
    assert '"$addFields": dict[str, Any],' in content
    assert 'MixedAggUnsetStage = TypedDict("MixedAggUnsetStage"' in content


def test_pipeline_stage_union_updated(tmp_path: Path):
    """PipelineStage union should include all safe stage types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineStage = " in content
    stage_section = content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedMatchStage" in stage_section
    assert "MixedSortStage" in stage_section
    assert "MixedLimitStage" in stage_section
    assert "MixedSkipStage" in stage_section
    assert "MixedSetStage" in stage_section
    assert "MixedAddFieldsStage" in stage_section
    assert "MixedAggUnsetStage" in stage_section


def test_runtime_has_aggregation_aliases(tmp_path: Path):
    """Runtime .py should have dict[str, Any] aliases for aggregation types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert "type MixedOptionalPath = str" in content
    assert "MixedMatchStage = dict[str, Any]" in content
    assert "MixedSortStage = dict[str, Any]" in content
    assert "MixedLimitStage = dict[str, Any]" in content
    assert "MixedSkipStage = dict[str, Any]" in content
    assert "MixedSetStage = dict[str, Any]" in content
    assert "MixedAddFieldsStage = dict[str, Any]" in content
    assert "MixedAggUnsetStage = dict[str, Any]" in content


# --- Task 8: unsafe stages and aggregation_step ---


def test_unsafe_stage_types(tmp_path: Path):
    """Stub should have model-specific unsafe stage TypedDicts."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedGroupStage = TypedDict("MixedGroupStage"' in content
    assert '"$group": MixedGroupFields,' in content
    assert "class MixedGroupFields(TypedDict):" in content
    assert 'MixedUnwindStage = TypedDict("MixedUnwindStage"' in content
    assert 'MixedProjectStage = TypedDict("MixedProjectStage"' in content
    assert 'MixedLookupStage = TypedDict("MixedLookupStage"' in content
    # LookupFields uses function-call syntax due to "from"/"as" keywords
    assert 'MixedLookupFields = TypedDict("MixedLookupFields"' in content
    assert '"localField": MixedPath,' in content
    assert 'MixedBucketStage = TypedDict("MixedBucketStage"' in content
    assert 'MixedBucketAutoStage = TypedDict("MixedBucketAutoStage"' in content


def test_aggregation_step_function_stub(tmp_path: Path):
    """Stub should have {name}_aggregation_step() function."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedUnsafeStage = " in content
    assert (
        "def mixed_aggregation_step(step: MixedUnsafeStage) -> AggregationStep: ..."
        in content
    )


def test_aggregation_step_function_runtime(tmp_path: Path):
    """Runtime .py should have {name}_aggregation_step() identity function."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert (
        "def mixed_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:" in content
    )
    assert "    return step" in content


# --- Task 10: compilation and edge cases ---


def test_generated_aggregation_code_compiles(tmp_path: Path):
    """Generated stub with all aggregation types should compile."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")

    runtime_content = runtime_path.read_text()
    compile(runtime_content, "<test>", "exec")


def test_no_optional_path_when_no_defaults(tmp_path: Path):
    """Models with no default fields should handle OptionalPath gracefully."""

    class _AllRequired(BaseModel):
        name: str
        age: int

    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"AllRequired": _AllRequired})

    content = stub_path.read_text()
    compile(content, "<test>", "exec")
    # PipelineStage should not include AggUnsetStage
    stage_section = content.split("type AllRequiredPipelineStage = (")[1].split(")")[0]
    assert "AggUnsetStage" not in stage_section
