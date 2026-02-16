"""Tests for field path collection from Pydantic models."""

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from typed_mongo_gen.introspect import collect_field_paths, collect_field_path_types


class _Leaf(BaseModel):
    model_config = {"alias_generator": to_camel}
    first_name: str
    age: int


class _Mid(BaseModel):
    model_config = {"alias_generator": to_camel}
    leaf: _Leaf
    tags: list[str] = Field(default_factory=list)


class _Root(BaseModel):
    model_config = {"alias_generator": to_camel}
    id: str = Field(validation_alias="_id", serialization_alias="_id")
    mid: _Mid
    items: list[_Leaf] = Field(default_factory=list)
    score: float | None = None


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
