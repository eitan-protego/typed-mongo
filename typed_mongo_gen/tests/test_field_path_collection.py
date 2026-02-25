"""Tests for field path collection from Pydantic models."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typed_mongo_gen.introspect import (
    collect_field_path_types,
    collect_field_paths,
    extract_list_element_type,
    is_numeric_type,
)


class _Leaf(BaseModel):
    first_name: str
    age: int

    model_config: ClassVar[ConfigDict] = {"alias_generator": to_camel}


class _Mid(BaseModel):
    leaf: _Leaf
    tags: list[str] = Field(default_factory=list)

    model_config: ClassVar[ConfigDict] = {"alias_generator": to_camel}


class _Root(BaseModel):
    id: str = Field(validation_alias="_id", serialization_alias="_id")
    mid: _Mid
    items: list[_Leaf] = Field(default_factory=list)
    score: float | None = None

    model_config: ClassVar[ConfigDict] = {"alias_generator": to_camel}


def test_flat_model():
    """Flat model should return all field names with aliases applied."""
    paths = collect_field_paths(_Leaf)
    assert paths == ["age", "firstName"]


def test_nested_model():
    """Nested model should include dotted paths."""
    paths = collect_field_paths(_Mid)
    assert "leaf" in paths
    assert "leaf.firstName" in paths
    assert "leaf.age" in paths
    assert "tags" in paths


def test_list_of_models_traversed():
    """list[Model] should be traversed transparently."""
    paths = collect_field_paths(_Root)
    assert "items" in paths
    assert "items.firstName" in paths
    assert "items.age" in paths


def test_id_alias():
    """Explicit serialization_alias should be used."""
    paths = collect_field_paths(_Root)
    assert "_id" in paths
    assert "id" not in paths


def test_optional_field_included():
    """Optional fields should be included in paths."""
    paths = collect_field_paths(_Root)
    assert "score" in paths


def test_flat_model_path_types():
    """collect_field_path_types should return {path: type} dict."""
    path_types = collect_field_path_types(_Leaf)
    assert path_types["firstName"] is str
    assert path_types["age"] is int


def test_nested_model_path_types():
    """Nested paths should resolve to leaf field types."""
    path_types = collect_field_path_types(_Mid)
    assert path_types["leaf.firstName"] is str
    assert path_types["leaf.age"] is int
    assert path_types["leaf"] is _Leaf
    assert path_types["tags"] == list[str]


def test_optional_field_type():
    """Optional fields should preserve union type."""
    path_types = collect_field_path_types(_Root)
    assert path_types["score"] == float | None


# --- is_numeric_type / extract_list_element_type tests ---


def test_is_numeric_type_int():
    assert is_numeric_type(int) is True

def test_is_numeric_type_float():
    assert is_numeric_type(float) is True

def test_is_numeric_type_optional_int():
    assert is_numeric_type(int | None) is True

def test_is_numeric_type_str():
    assert is_numeric_type(str) is False

def test_is_numeric_type_list_int():
    """list[int] is NOT numeric — it's an array field."""
    assert is_numeric_type(list[int]) is False

def test_is_numeric_type_optional_float():
    assert is_numeric_type(float | None) is True

def test_is_numeric_type_union_str_int():
    """str | int has a numeric member, so it's numeric."""
    assert is_numeric_type(str | int) is True


def test_extract_list_element_type_simple():
    assert extract_list_element_type(list[str]) is str

def test_extract_list_element_type_int():
    assert extract_list_element_type(list[int]) is int

def test_extract_list_element_type_not_list():
    assert extract_list_element_type(str) is None

def test_extract_list_element_type_optional_list():
    """list[str] | None should still extract str."""
    result = extract_list_element_type(list[str] | None)
    assert result is str

def test_extract_list_element_type_bare_list():
    assert extract_list_element_type(list) is None
