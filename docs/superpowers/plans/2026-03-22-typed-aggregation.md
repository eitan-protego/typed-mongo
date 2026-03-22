# Typed Aggregation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add type-safe aggregation pipeline support with per-model codegen'd stage types, overloaded aggregate() method, and base library AggregationStep union.

**Architecture:** Three-layer approach — (1) base `AggregationStep` union in `operators.py` for structural stage validation, (2) 7th type parameter + overloaded `aggregate()` on `TypedCollection`, (3) codegen of per-model safe/unsafe stage TypedDicts and helper functions. All new complex types live in `.pyi` stubs only; runtime `.py` uses `dict[str, Any]` aliases.

**Tech Stack:** Python 3.12+, PEP 695 generics, PEP 728 `closed`/`extra_items` via `typing_extensions.TypedDict`, basedpyright, pydantic v2, pymongo async.

**Spec:** `docs/superpowers/specs/2026-03-22-typed-aggregation-design.md`

---

### Task 1: Add `AggregationStep` to `operators.py`

**Files:**
- Modify: `typed_mongo/src/typed_mongo/operators.py:67` (after `AggExprOp`)
- Modify: `typed_mongo/src/typed_mongo/__init__.py:5-19` (add export)
- Test: `typed_mongo/tests/test_operators.py`

- [ ] **Step 1: Write failing tests for AggregationStep**

Add to `typed_mongo/tests/test_operators.py`:

```python
def test_aggregation_step_types_exist():
    """AggregationStep and individual stage TypedDicts should be importable."""
    from typed_mongo.operators import (
        AggregationStep,
        GroupStage,
        BucketStage,
        BucketAutoStage,
        UnwindStage,
        ProjectStage,
        LookupStage,
        MatchStage,
        SortStage,
        LimitStage,
        SkipStage,
        SetStage,
        AddFieldsStage,
        UnsetStage,
        CountStage,
    )
    # Verify they are all types (TypedDict classes or type aliases)
    assert AggregationStep is not None
    assert GroupStage is not None


def test_group_stage_requires_id():
    """GroupStage should accept a dict with _id key."""
    from typed_mongo.operators import GroupStage
    stage: GroupStage = {"$group": {"_id": "$field", "count": {"$sum": 1}}}
    assert "$group" in stage


def test_limit_stage_accepts_int():
    """LimitStage should accept an int."""
    from typed_mongo.operators import LimitStage
    stage: LimitStage = {"$limit": 10}
    assert stage["$limit"] == 10


def test_skip_stage_accepts_int():
    """SkipStage should accept an int."""
    from typed_mongo.operators import SkipStage
    stage: SkipStage = {"$skip": 5}
    assert stage["$skip"] == 5


def test_aggregation_step_accepts_group():
    """AggregationStep union should accept a GroupStage."""
    from typed_mongo.operators import AggregationStep
    step: AggregationStep = {"$group": {"_id": "$x"}}
    assert "$group" in step


def test_aggregation_step_accepts_limit():
    """AggregationStep union should accept a LimitStage."""
    from typed_mongo.operators import AggregationStep
    step: AggregationStep = {"$limit": 10}
    assert "$limit" in step
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo/tests/test_operators.py::test_aggregation_step_types_exist -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement AggregationStep and all stage TypedDicts**

Add to `typed_mongo/src/typed_mongo/operators.py` after the `AggExprOp` block (after line 67):

**Note:** The base library stage TypedDicts intentionally do NOT use `closed=True` because `operators.py` uses `typing.TypedDict` (not `typing_extensions.TypedDict`). Adding `typing_extensions` as a dependency of the base `typed-mongo` package would be unnecessary — `closed` is only needed in the codegen'd `.pyi` stubs which already use `typing_extensions.TypedDict`.

```python
from typing import NotRequired


# --- Aggregation pipeline stage types ---
# Structurally validated stages (also have model-specific codegen helpers)

class GroupStageValue(TypedDict):
    _id: Any

GroupStage = TypedDict("GroupStage", {"$group": GroupStageValue})

BucketStageValue = TypedDict("BucketStageValue", {
    "groupBy": Any,
    "boundaries": list[Any],
    "default": Any,
    "output": NotRequired[dict[str, Any]],
})
BucketStage = TypedDict("BucketStage", {"$bucket": BucketStageValue})

class BucketAutoStageValue(TypedDict):
    groupBy: Any
    buckets: int

BucketAutoStage = TypedDict("BucketAutoStage", {"$bucketAuto": BucketAutoStageValue})

UnwindStage = TypedDict("UnwindStage", {"$unwind": str | dict[str, Any]})

ProjectStage = TypedDict("ProjectStage", {"$project": dict[str, Any]})

LookupStageValue = TypedDict("LookupStageValue", {
    "from": str,
    "localField": str,
    "foreignField": str,
    "as": str,
})
LookupStage = TypedDict("LookupStage", {"$lookup": LookupStageValue})

# Minimally annotated stages
MatchStage = TypedDict("MatchStage", {"$match": dict[str, Any]})
SortStage = TypedDict("SortStage", {"$sort": dict[str, int]})
LimitStage = TypedDict("LimitStage", {"$limit": int})
SkipStage = TypedDict("SkipStage", {"$skip": int})
SetStage = TypedDict("SetStage", {"$set": dict[str, Any]})
AddFieldsStage = TypedDict("AddFieldsStage", {"$addFields": dict[str, Any]})
UnsetStage = TypedDict("UnsetStage", {"$unset": str | list[str]})
CountStage = TypedDict("CountStage", {"$count": str})
ReplaceRootStage = TypedDict("ReplaceRootStage", {"$replaceRoot": dict[str, Any]})
ReplaceWithStage = TypedDict("ReplaceWithStage", {"$replaceWith": dict[str, Any]})
OutStage = TypedDict("OutStage", {"$out": str | dict[str, Any]})
MergeStage = TypedDict("MergeStage", {"$merge": str | dict[str, Any]})
FacetStage = TypedDict("FacetStage", {"$facet": dict[str, list[Any]]})
GraphLookupStage = TypedDict("GraphLookupStage", {"$graphLookup": dict[str, Any]})
RedactStage = TypedDict("RedactStage", {"$redact": dict[str, Any]})
SampleStage = TypedDict("SampleStage", {"$sample": dict[str, int]})
UnionWithStage = TypedDict("UnionWithStage", {"$unionWith": str | dict[str, Any]})
SortByCountStage = TypedDict("SortByCountStage", {"$sortByCount": str | dict[str, Any]})
GeoNearStage = TypedDict("GeoNearStage", {"$geoNear": dict[str, Any]})
DensifyStage = TypedDict("DensifyStage", {"$densify": dict[str, Any]})
FillStage = TypedDict("FillStage", {"$fill": dict[str, Any]})
DocumentsStage = TypedDict("DocumentsStage", {"$documents": list[dict[str, Any]]})
SetWindowFieldsStage = TypedDict("SetWindowFieldsStage", {"$setWindowFields": dict[str, Any]})
ChangeStreamStage = TypedDict("ChangeStreamStage", {"$changeStream": dict[str, Any]})
CollStatsStage = TypedDict("CollStatsStage", {"$collStats": dict[str, Any]})
CurrentOpStage = TypedDict("CurrentOpStage", {"$currentOp": dict[str, Any]})
IndexStatsStage = TypedDict("IndexStatsStage", {"$indexStats": dict[str, Any]})
ListSessionsStage = TypedDict("ListSessionsStage", {"$listSessions": dict[str, Any]})
PlanCacheStatsStage = TypedDict("PlanCacheStatsStage", {"$planCacheStats": dict[str, Any]})
SearchStage = TypedDict("SearchStage", {"$search": dict[str, Any]})
SearchMetaStage = TypedDict("SearchMetaStage", {"$searchMeta": dict[str, Any]})

type AggregationStep = (
    GroupStage | BucketStage | BucketAutoStage | UnwindStage | ProjectStage | LookupStage
    | MatchStage | SortStage | LimitStage | SkipStage | SetStage | AddFieldsStage
    | UnsetStage | CountStage | ReplaceRootStage | ReplaceWithStage | OutStage | MergeStage
    | FacetStage | GraphLookupStage | RedactStage | SampleStage | UnionWithStage
    | SortByCountStage | GeoNearStage | DensifyStage | FillStage | DocumentsStage
    | SetWindowFieldsStage | ChangeStreamStage | CollStatsStage | CurrentOpStage
    | IndexStatsStage | ListSessionsStage | PlanCacheStatsStage | SearchStage | SearchMetaStage
)
```

Also add `NotRequired` to the import on line 13:
```python
from typing import Any, Literal, NotRequired, TypedDict, cast
```

- [ ] **Step 4: Export AggregationStep from `__init__.py`**

Add `AggregationStep` to the import and `__all__` in `typed_mongo/src/typed_mongo/__init__.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest typed_mongo/tests/test_operators.py -v`
Expected: All tests PASS

- [ ] **Step 6: Fix existing test for type param count**

The test `test_typed_collection_has_six_type_params` at `typed_mongo/tests/test_operators.py:171` will fail in Task 2 when we add the 7th param. For now, just confirm all tests pass.

- [ ] **Step 7: Commit**

```bash
git add typed_mongo/src/typed_mongo/operators.py typed_mongo/src/typed_mongo/__init__.py typed_mongo/tests/test_operators.py
git commit -m "feat: add AggregationStep union type with all MongoDB stage TypedDicts"
```

---

### Task 2: Add 7th type parameter and overloaded `aggregate()` to `TypedCollection`

**Files:**
- Modify: `typed_mongo/src/typed_mongo/collection.py:72-79` (type params), `collection.py:103-109` (from_database), `collection.py:135-139` (aggregate)
- Modify: `typed_mongo/tests/test_operators.py:171-180` (update type param count test)
- Test: `typed_mongo/tests/test_operators.py`

- [ ] **Step 1: Write failing tests for 7th type param and aggregate overloads**

Add to `typed_mongo/tests/test_operators.py`:

```python
def test_typed_collection_has_seven_type_params():
    """TypedCollection should accept M, Model, Path, Query, Fields, Update, PipelineStage params."""
    params = TypedCollection.__type_params__
    assert len(params) == 7
    assert params[6].__name__ == "PipelineStage"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo/tests/test_operators.py::test_typed_collection_has_seven_type_params -v`
Expected: FAIL with AssertionError (6 != 7)

- [ ] **Step 3: Add PipelineStage type parameter to TypedCollection**

Edit `typed_mongo/src/typed_mongo/collection.py`:

Replace lines 72-79 with:
```python
class TypedCollection[
    M: MongoCollectionModel,
    Model: Mapping[str, Any],
    Path: str,
    Query: Mapping[str, Any],
    Fields: Mapping[str, Any],
    Update: Mapping[str, Any],
    PipelineStage: Mapping[str, Any],
]:
```

Update the docstring (lines 80-93) to add:
```
        PipelineStage: Pipeline stage TypedDict union for type-safe aggregation
```

Update `from_database` return type (line 106):
```python
    ) -> TypedCollection[M, Any, Any, Any, Any, Any, Any]:
```

- [ ] **Step 4: Replace aggregate() with overloaded version**

Add `overload` to imports at line 19:
```python
from typing import Any, overload
```

Add `AggregationStep` import:
```python
from typed_mongo.operators import AggregationStep
```

Replace lines 135-139 with:
```python
    @overload
    async def aggregate(self, pipeline: list[PipelineStage]) -> TypedCursor[M]: ...

    @overload
    async def aggregate(
        self,
        pipeline: list[PipelineStage],
        type_unsafe_pipeline_suffix: list[AggregationStep],
    ) -> AsyncCursor[dict[str, Any]]: ...

    async def aggregate(
        self,
        pipeline: list[PipelineStage],
        type_unsafe_pipeline_suffix: list[AggregationStep] | None = None,
    ) -> TypedCursor[M] | AsyncCursor[dict[str, Any]]:
        """Run an aggregation pipeline.

        With only safe pipeline stages, returns TypedCursor[M] that validates
        results as model instances. With type_unsafe_pipeline_suffix, returns
        a raw AsyncCursor since the output shape is unknown.
        """
        full_pipeline: list[dict[str, Any]] = list(pipeline)  # pyright: ignore[reportAssignmentType]
        if type_unsafe_pipeline_suffix:
            full_pipeline.extend(type_unsafe_pipeline_suffix)  # pyright: ignore[reportAssignmentType]
            return await self._collection.aggregate(full_pipeline)
        return TypedCursor(self._model, await self._collection.aggregate(full_pipeline))
```

- [ ] **Step 5: Update existing test for type param count**

Replace `test_typed_collection_has_six_type_params` (lines 171-180) with:
```python
def test_typed_collection_has_seven_type_params():
    """TypedCollection should accept M, Model, Path, Query, Fields, Update, PipelineStage params."""
    params = TypedCollection.__type_params__
    assert len(params) == 7
    assert params[0].__name__ == "M"
    assert params[1].__name__ == "Model"
    assert params[2].__name__ == "Path"
    assert params[3].__name__ == "Query"
    assert params[4].__name__ == "Fields"
    assert params[5].__name__ == "Update"
    assert params[6].__name__ == "PipelineStage"
```

Remove the old `test_typed_collection_has_six_type_params` test, and remove the duplicate `test_typed_collection_has_seven_type_params` added in step 1.

Also remove the stale `test_typed_collection_has_dump` test (line 193-195) — the `dump()` method was already removed from TypedCollection in a prior refactor.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest typed_mongo/tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add typed_mongo/src/typed_mongo/collection.py typed_mongo/tests/test_operators.py
git commit -m "feat: add 7th PipelineStage type param and overloaded aggregate()"
```

---

### Task 3: Extend `_write_typeddict` for PEP 728 `closed` and `extra_items`

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:35-63` (`_write_typeddict`)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing test for closed TypedDict generation**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
from typed_mongo_gen.codegen import _write_typeddict
import io


def test_write_typeddict_closed():
    """_write_typeddict should support closed=True parameter."""
    f = io.StringIO()
    _write_typeddict(f, "TestStage", [("$match", "dict[str, Any]")], closed=True)
    content = f.getvalue()
    assert "closed=True" in content
    # $ key -> function-call syntax
    assert 'TestStage = TypedDict("TestStage"' in content


def test_write_typeddict_extra_items():
    """_write_typeddict should support extra_items parameter."""
    f = io.StringIO()
    _write_typeddict(f, "TestFields", [("name", "str")], total=False, closed=True, extra_items="Any")
    content = f.getvalue()
    assert "closed=True" in content
    assert "extra_items=Any" in content


def test_write_typeddict_closed_class_syntax():
    """closed=True should work with class syntax (valid identifier keys)."""
    f = io.StringIO()
    _write_typeddict(f, "TestFields", [("name", "str"), ("age", "int")], closed=True)
    content = f.getvalue()
    assert "class TestFields(TypedDict, closed=True):" in content
    assert "    name: str" in content
    assert "    age: int" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_write_typeddict_closed -v`
Expected: FAIL with TypeError (unexpected keyword argument 'closed')

- [ ] **Step 3: Extend `_write_typeddict` to accept `closed` and `extra_items`**

Replace the `_write_typeddict` function at `codegen.py:35-63`:

```python
def _write_typeddict(
    f: typing.TextIO,
    name: str,
    entries: list[tuple[str, str]],
    *,
    total: bool = True,
    closed: bool = False,
    extra_items: str | None = None,
) -> None:
    """Write a TypedDict using class syntax if possible, else function-call syntax."""
    keys = [k for k, _ in entries]

    # Build extra keyword args string
    extra_kwargs = ""
    if not total:
        extra_kwargs += ", total=False"
    if closed:
        extra_kwargs += ", closed=True"
    if extra_items is not None:
        extra_kwargs += f", extra_items={extra_items}"

    if not entries:
        # Empty TypedDict — always use function-call syntax
        f.write(f'{name} = TypedDict("{name}", {{}}{extra_kwargs})\n\n')
        return

    if _all_valid_identifiers(keys):
        # Class syntax
        f.write(f"class {name}(TypedDict{extra_kwargs}):\n")
        for key, type_str in entries:
            f.write(f"    {key}: {type_str}\n")
        f.write("\n")
    else:
        # Function-call syntax
        f.write(f'{name} = TypedDict("{name}", {{\n')
        for key, type_str in entries:
            f.write(f'    "{key}": {type_str},\n')
        f.write(f"}}{extra_kwargs})\n\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: extend _write_typeddict for PEP 728 closed and extra_items"
```

---

### Task 4: Update stub header to import `typing_extensions` and `AggregationStep`

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:260-316` (`_write_headers`)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing test for updated header imports**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_stub_header_imports_typing_extensions(tmp_path: Path):
    """Stub should import TypedDict from typing_extensions for PEP 728 support."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"TestModel": _TestModel})

    content = stub_path.read_text()
    assert "from typing_extensions import NotRequired, Required, TypedDict" in content
    assert "from typed_mongo.operators import AggExprOp, AggregationStep, Op" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_stub_header_imports_typing_extensions -v`
Expected: FAIL

- [ ] **Step 3: Update `_write_headers`**

In `codegen.py`, modify `_write_headers` (around line 288-316):

1. Change the `typing_names` handling (around line 292-294) to exclude `TypedDict` from `typing` imports (it now comes from `typing_extensions`):
```python
    typing_names = {n for m, n in all_imports if m == "typing"}
    typing_names |= {"Literal", "Any", "overload"}
    typing_names -= {"TypedDict"}  # TypedDict comes from typing_extensions
    stub_f.write(f"from typing import {', '.join(sorted(typing_names))}\n")
    stub_f.write("from typing_extensions import NotRequired, Required, TypedDict\n")
```

2. Update the operators import line (line 315):
```python
    stub_f.write("from typed_mongo.operators import AggExprOp, AggregationStep, Op\n")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS. Some existing tests that check for `from typing import ... TypedDict` may need updating if they assert the old import line.

- [ ] **Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: import TypedDict from typing_extensions and AggregationStep in stub header"
```

---

### Task 5: Add `has_default` introspection helper

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/introspect.py` (add function)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing test**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
from typed_mongo_gen.introspect import has_default


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_has_default_with_default_value -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `has_default`**

Add to `typed_mongo_gen/src/typed_mongo_gen/introspect.py`:

```python
from pydantic_core import PydanticUndefined


def has_default(model: type[BaseModel], field_name: str) -> bool:
    """Check if a field has a default value (not required when absent from document).

    Returns True if the field has an explicit default value or a default_factory.
    """
    field_info = model.model_fields[field_name]
    return (
        field_info.default is not PydanticUndefined
        or field_info.default_factory is not None
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_has_default_with_default_value -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/introspect.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: add has_default introspection helper for optional field detection"
```

---

### Task 6: Generate per-type RefPaths and updated PipelineSetFields

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:336-482` (`_write_model`)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

This task replaces the single `{Name}RefPath` with per-type variants and updates `PipelineSetFields` to use them with `closed=True, extra_items=Any`.

- [ ] **Step 1: Write failing tests**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_per_type_ref_paths(tmp_path: Path):
    """Stub should have per-type RefPath Literals grouping fields by value type."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # str fields: name
    assert "type MixedStrRefPath = Literal[" in content
    assert '"$name"' in content
    # int | None field: age
    assert "type MixedIntNoneRefPath = Literal[" in content or "type MixedIntOrNoneRefPath = Literal[" in content
    # float field: score
    assert "type MixedFloatRefPath = Literal[" in content
    # The generic RefPath should still exist for unsafe helpers
    assert "type MixedRefPath = Literal[" in content


def test_pipeline_set_fields_uses_typed_refs(tmp_path: Path):
    """PipelineSetFields should use per-type RefPaths and have closed=True, extra_items=Any."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # Should use closed=True and extra_items=Any
    assert "closed=True" in content
    assert "extra_items=Any" in content
    # name field should reference str-typed RefPath, not the generic MixedRefPath
    assert "MixedRefPath | Mapping[AggExprOp, Any]" not in content.split("PipelineSetFields")[1].split(")\n")[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_per_type_ref_paths -v`
Expected: FAIL

- [ ] **Step 3: Implement per-type RefPaths generation**

In `_write_model` in `codegen.py`, after the existing RefPath generation (around line 438-442), add logic to group fields by their annotation source string and emit per-type RefPath Literals.

The approach:
1. Group `path_types` by their `_annotation_to_source()` output (with `model_dict_names`).
2. For each unique type string, create a sanitized name (e.g., `str` -> `Str`, `int | None` -> `IntOrNone`, `float` -> `Float`).
3. Emit `type {model_name}{SanitizedType}RefPath = Literal["$field1", "$field2", ...]`.
4. Store a mapping of `path -> typed_ref_path_name` for use in PipelineSetFields.

Add a helper function before `_write_model`:

```python
def _sanitize_type_name(type_src: str) -> str:
    """Convert a type source string to a valid identifier for use in RefPath names.

    E.g., 'str' -> 'Str', 'int | None' -> 'IntOrNone', 'list[str]' -> 'ListStr'.
    """
    # Replace common patterns
    name = type_src.replace(" | ", "Or").replace("[", "").replace("]", "").replace(", ", "And")
    # Capitalize first letter of each word
    parts = name.split("Or")
    parts = [p[0].upper() + p[1:] if p else p for p in parts]
    return "Or".join(parts)
```

Then in `_write_model`, after the RefPath block and before PipelineSetFields:

```python
    # Per-type RefPaths: group fields by value type for type-safe $set refs
    type_to_paths: dict[str, list[str]] = {}
    for path in sorted(path_types):
        if "." in path:
            continue  # Only top-level fields for RefPaths
        type_src = _annotation_to_source(path_types[path], module_aliases, model_dict_names)
        type_to_paths.setdefault(type_src, []).append(path)

    path_to_typed_ref: dict[str, str] = {}
    for type_src, type_paths in type_to_paths.items():
        sanitized = _sanitize_type_name(type_src)
        ref_name = f"{model_name}{sanitized}RefPath"
        stub_f.write(f"type {ref_name} = Literal[\n")
        for path in type_paths:
            stub_f.write(f'    "${path}",\n')
        stub_f.write("]\n\n")
        for path in type_paths:
            path_to_typed_ref[path] = ref_name
```

Then update PipelineSetFields generation (replacing lines 444-449) to use typed refs and PEP 728:

```python
    # PipelineSetFields TypedDict (T | TypedRefPath | Mapping[AggExprOp, Any])
    pipeline_set_entries = []
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path], module_aliases, model_dict_names)
        # Use per-type ref path for top-level fields, generic RefPath for nested paths
        ref_path_name = path_to_typed_ref.get(path, f"{model_name}RefPath")
        pipeline_set_entries.append(
            (path, f"{type_src} | {ref_path_name} | Mapping[AggExprOp, Any]")
        )
    _write_typeddict(
        stub_f, f"{model_name}PipelineSetFields", pipeline_set_entries,
        total=False, closed=True, extra_items="Any",
    )
```

- [ ] **Step 4: Update existing test that checks PipelineSetFields**

The test `test_pipeline_set_fields_typed_dict` (line 285) asserts `MixedRefPath` in the output. Update it to check for the per-type ref path instead:

```python
def test_pipeline_set_fields_typed_dict(tmp_path: Path):
    """Stub should have PipelineSetFields with T | TypedRefPath | Mapping[AggExprOp, Any]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # Should use closed=True and extra_items=Any
    assert "closed=True" in content
    assert "extra_items=Any" in content
    # name is str -> should ref MixedStrRefPath
    assert "MixedStrRefPath | Mapping[AggExprOp, Any]" in content
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: generate per-type RefPaths and update PipelineSetFields with PEP 728"
```

---

### Task 7: Generate OptionalPath and safe aggregation stage TypedDicts

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:336-482` (`_write_model`)
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:346-369` (runtime aliases)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing tests**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_optional_path_literal(tmp_path: Path):
    """Stub should have OptionalPath with only fields that have defaults."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedOptionalPath = Literal[" in content
    # _ModelWithMixedFields: age has default None, score has default 0.0,
    # tags has default [], active has default True
    # name has NO default
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
    assert '"$addFields": MixedPipelineSetFields,' in content
    assert 'MixedAggUnsetStage = TypedDict("MixedAggUnsetStage"' in content


def test_pipeline_stage_union_updated(tmp_path: Path):
    """PipelineStage union should include all safe stage types."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineStage = " in content
    assert "MixedMatchStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedSortStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedLimitStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedSkipStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedSetStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedAddFieldsStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]
    assert "MixedAggUnsetStage" in content.split("type MixedPipelineStage = ")[1].split("\n\n")[0]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_optional_path_literal -v`
Expected: FAIL

- [ ] **Step 3: Implement OptionalPath and safe stage generation**

In `_write_model`, add the import of `has_default` at the top of `codegen.py`:
```python
from typed_mongo_gen.introspect import (
    _extract_base_models,
    _resolve_alias,
    collect_field_path_types,
    collect_field_paths,
    extract_list_element_type,
    has_default,
    is_numeric_type,
)
```

Then in `_write_model`, after the PipelineSetFields block, replace the existing pipeline stage generation (lines 467-471) with:

```python
    # OptionalPath: fields with defaults (can be safely $unset in aggregation)
    optional_paths = [
        _resolve_alias(model, fname)
        for fname in model.model_fields
        if has_default(model, fname)
    ]
    if optional_paths:
        stub_f.write(f"type {model_name}OptionalPath = Literal[\n")
        for path in sorted(optional_paths):
            stub_f.write(f'    "{path}",\n')
        stub_f.write("]\n\n")
    else:
        stub_f.write(f"type {model_name}OptionalPath = str  # no optional fields\n\n")

    # Safe aggregation stage TypedDicts
    _write_typeddict(stub_f, f"{model_name}MatchStage", [("$match", f"{model_name}Query")], closed=True)
    _write_typeddict(stub_f, f"{model_name}SortStage", [("$sort", f"dict[{model_name}Path, Literal[1, -1]]")], closed=True)
    _write_typeddict(stub_f, f"{model_name}LimitStage", [("$limit", "int")], closed=True)
    _write_typeddict(stub_f, f"{model_name}SkipStage", [("$skip", "int")], closed=True)
    _write_typeddict(stub_f, f"{model_name}SetStage", [("$set", f"{model_name}PipelineSetFields")], closed=True)
    _write_typeddict(stub_f, f"{model_name}AddFieldsStage", [("$addFields", f"{model_name}PipelineSetFields")], closed=True)
    if optional_paths:
        _write_typeddict(stub_f, f"{model_name}AggUnsetStage", [("$unset", f"{model_name}OptionalPath | list[{model_name}OptionalPath]")], closed=True)

    # PipelineStage union (safe stages only)
    safe_stages = [
        f"{model_name}MatchStage",
        f"{model_name}SortStage",
        f"{model_name}LimitStage",
        f"{model_name}SkipStage",
        f"{model_name}SetStage",
        f"{model_name}AddFieldsStage",
    ]
    if optional_paths:
        safe_stages.append(f"{model_name}AggUnsetStage")
    stub_f.write(f"type {model_name}PipelineStage = (\n")
    for i, stage in enumerate(safe_stages):
        prefix = "    " if i == 0 else "    | "
        stub_f.write(f"{prefix}{stage}\n")
    stub_f.write(")\n\n")
```

Remove the old `PipelineSet`, `PipelineUnset`, and `PipelineStage` generation (the lines that were at 467-471).

Also add runtime aliases in the runtime block (around lines 346-369). After the existing `PipelineUnset` line add:

```python
    runtime_f.write(f"type {model_name}OptionalPath = str\n")
    runtime_f.write(f"{model_name}MatchStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SortStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LimitStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SkipStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SetStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}AddFieldsStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}AggUnsetStage = dict[str, Any]\n")
```

- [ ] **Step 4: Update existing `test_pipeline_stage_union` test**

Replace the existing `test_pipeline_stage_union` test (line 298) to check for the new union format:

```python
def test_pipeline_stage_union(tmp_path: Path):
    """Stub should have PipelineStage union with all safe stages."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedPipelineStage = (" in content
    assert "MixedMatchStage" in content
    assert "MixedSortStage" in content
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: generate OptionalPath and safe aggregation stage TypedDicts"
```

---

### Task 8: Generate model-specific unsafe stage helpers and `{name}_aggregation_step()`

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py` (`_write_model`)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing tests**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_unsafe_stage_types(tmp_path: Path):
    """Stub should have model-specific unsafe stage TypedDicts."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    # Group stage
    assert 'MixedGroupStage = TypedDict("MixedGroupStage"' in content
    assert '"$group": MixedGroupFields,' in content
    assert "class MixedGroupFields(TypedDict, closed=True):" in content
    # Unwind stage
    assert 'MixedUnwindStage = TypedDict("MixedUnwindStage"' in content
    # Project stage
    assert 'MixedProjectStage = TypedDict("MixedProjectStage"' in content
    # Lookup stage
    assert 'MixedLookupStage = TypedDict("MixedLookupStage"' in content
    assert '"localField": MixedPath,' in content
    # Bucket stages
    assert 'MixedBucketStage = TypedDict("MixedBucketStage"' in content
    assert 'MixedBucketAutoStage = TypedDict("MixedBucketAutoStage"' in content


def test_aggregation_step_function_stub(tmp_path: Path):
    """Stub should have {name}_aggregation_step() function."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert "type MixedUnsafeStage = " in content
    assert "def mixed_aggregation_step(step: MixedUnsafeStage) -> AggregationStep: ..." in content


def test_aggregation_step_function_runtime(tmp_path: Path):
    """Runtime .py should have {name}_aggregation_step() identity function."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = runtime_path.read_text()
    assert "def mixed_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:" in content
    assert "    return step" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_unsafe_stage_types -v`
Expected: FAIL

- [ ] **Step 3: Implement unsafe stage generation**

In `_write_model`, after the PipelineStage union, add:

```python
    # --- Model-specific unsafe stage helpers ---
    # These check field references in inputs but produce unknowable output shapes

    # $group — _id checked against RefPath
    _write_typeddict(stub_f, f"{model_name}GroupFields", [
        ("_id", f"{model_name}RefPath | list[{model_name}RefPath] | dict[str, {model_name}RefPath] | None"),
    ], closed=True)
    _write_typeddict(stub_f, f"{model_name}GroupStage", [
        ("$group", f"{model_name}GroupFields"),
    ], closed=True)

    # $unwind — path checked against RefPath, supports string and object form
    _write_typeddict(stub_f, f"{model_name}UnwindOptions", [
        ("path", f"Required[{model_name}RefPath]"),
        ("preserveNullAndEmptyArrays", "bool"),
        ("includeArrayIndex", "str"),
    ], total=False, closed=True)
    _write_typeddict(stub_f, f"{model_name}UnwindStage", [
        ("$unwind", f"{model_name}RefPath | {model_name}UnwindOptions"),
    ], closed=True)

    # $project — field names checked against Path
    _write_typeddict(stub_f, f"{model_name}ProjectStage", [
        ("$project", f"dict[{model_name}Path, Literal[0, 1] | dict[str, Any]]"),
    ], closed=True)

    # $bucket — groupBy checked against RefPath
    _write_typeddict(stub_f, f"{model_name}BucketFields", [
        ("groupBy", f"{model_name}RefPath"),
        ("boundaries", "list[Any]"),
        ("default", "Any"),
        ("output", "NotRequired[dict[str, Any]]"),
    ], closed=True)
    _write_typeddict(stub_f, f"{model_name}BucketStage", [
        ("$bucket", f"{model_name}BucketFields"),
    ], closed=True)

    # $bucketAuto — groupBy checked against RefPath
    _write_typeddict(stub_f, f"{model_name}BucketAutoFields", [
        ("groupBy", f"{model_name}RefPath"),
        ("buckets", "int"),
    ], closed=True)
    _write_typeddict(stub_f, f"{model_name}BucketAutoStage", [
        ("$bucketAuto", f"{model_name}BucketAutoFields"),
    ], closed=True)

    # $lookup — localField checked against Path
    _write_typeddict(stub_f, f"{model_name}LookupFields", [
        ("from", "str"),
        ("localField", f"{model_name}Path"),
        ("foreignField", "str"),
        ("as", "str"),
    ], closed=True)
    _write_typeddict(stub_f, f"{model_name}LookupStage", [
        ("$lookup", f"{model_name}LookupFields"),
    ], closed=True)

    # UnsafeStage union and aggregation_step function
    unsafe_stages = [
        f"{model_name}GroupStage",
        f"{model_name}UnwindStage",
        f"{model_name}ProjectStage",
        f"{model_name}BucketStage",
        f"{model_name}BucketAutoStage",
        f"{model_name}LookupStage",
    ]
    stub_f.write(f"type {model_name}UnsafeStage = (\n")
    for i, stage in enumerate(unsafe_stages):
        prefix = "    " if i == 0 else "    | "
        stub_f.write(f"{prefix}{stage}\n")
    stub_f.write(")\n\n")

    # Convert model name to snake_case for function name
    func_name = _to_snake_case(model_name)
    stub_f.write(f"def {func_name}_aggregation_step(step: {model_name}UnsafeStage) -> AggregationStep: ...\n\n")
```

Add a `_to_snake_case` helper before `_write_model`:

```python
import re

def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name)
    s = re.sub(r'(?<=[A-Z])([A-Z][a-z])', r'_\1', s)
    return s.lower()
```

Add runtime aliases and function in the runtime block:

```python
    runtime_f.write(f"{model_name}GroupStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}GroupFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnwindStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnwindOptions = dict[str, Any]\n")
    runtime_f.write(f"{model_name}ProjectStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketAutoStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketAutoFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LookupStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LookupFields = dict[str, Any]\n")
    func_name = _to_snake_case(model_name)
    runtime_f.write(f"type {model_name}UnsafeStage = dict[str, Any]\n")
    runtime_f.write(f"\n\ndef {func_name}_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:\n")
    runtime_f.write("    return step\n\n\n")
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: generate model-specific unsafe stages and aggregation_step() helper"
```

---

### Task 9: Update Collection class generation to use 7 type params

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:473-482` (Collection class generation)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

- [ ] **Step 1: Write failing test**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_collection_stub_has_seven_type_params(tmp_path: Path):
    """Generated Collection stub should use all 7 type params including PipelineStage."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    expected = "TypedCollection[_ModelWithMixedFields, MixedDict, MixedPath, MixedQuery, MixedFields, MixedUpdate, MixedPipelineStage]"
    assert expected in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_collection_stub_has_seven_type_params -v`
Expected: FAIL (still has 6 params)

- [ ] **Step 3: Update Collection class generation**

In `_write_model`, update the Collection class generation (around line 475-482):

Replace:
```python
        + f"TypedCollection[{model_ref}, {model_name}Dict, {model_name}Path, {model_name}Query, {model_name}Fields, {model_name}Update]"
```

With:
```python
        + f"TypedCollection[{model_ref}, {model_name}Dict, {model_name}Path, {model_name}Query, {model_name}Fields, {model_name}Update, {model_name}PipelineStage]"
```

- [ ] **Step 4: Update existing test `test_collection_stub_has_six_type_params`**

Remove or update the old test at line 311 that checks for 6 params:

```python
def test_collection_stub_has_seven_type_params(tmp_path: Path):
    """Generated Collection stub should use all 7 type params including PipelineStage."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    expected = "TypedCollection[_ModelWithMixedFields, MixedDict, MixedPath, MixedQuery, MixedFields, MixedUpdate, MixedPipelineStage]"
    assert expected in content
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: update generated Collection class to 7 type params"
```

---

### Task 10: Generated code compilation and full test suite

**Files:**
- Test: `typed_mongo_gen/tests/test_code_generation.py`
- Test: `typed_mongo/tests/test_operators.py`

- [ ] **Step 1: Write compilation test for new generated code**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
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
    # Should still compile
    compile(content, "<test>", "exec")
    # PipelineStage should not include AggUnsetStage
    stage_section = content.split("type AllRequiredPipelineStage = (")[1].split(")")[0]
    assert "AggUnsetStage" not in stage_section
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS across both packages

- [ ] **Step 3: Commit**

```bash
git add typed_mongo_gen/tests/test_code_generation.py
git commit -m "test: add compilation and edge case tests for aggregation codegen"
```

---

### Task 11: Add `typing_extensions` dependency to `typed_mongo_gen`

**Files:**
- Modify: `typed_mongo_gen/pyproject.toml:10`

- [ ] **Step 1: Add dependency**

Add `typing_extensions>=4.10` to the dependencies list in `typed_mongo_gen/pyproject.toml`:

```toml
dependencies = ["typed-mongo", "pydantic>=2.0", "cyclopts>=2.0", "typing_extensions>=4.10"]
```

- [ ] **Step 2: Sync lockfile**

Run: `uv sync`
Expected: Success (typing_extensions is already in the lockfile)

- [ ] **Step 3: Commit**

```bash
git add typed_mongo_gen/pyproject.toml uv.lock
git commit -m "chore: add typing_extensions dependency to typed_mongo_gen"
```

---

### Task 12: Final integration validation

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Run basedpyright type checker**

Run: `uv run basedpyright typed_mongo/src/ typed_mongo_gen/src/`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 3: Run ruff linter**

Run: `uv run ruff check typed_mongo/src/ typed_mongo_gen/src/`
Expected: No errors

- [ ] **Step 4: Final commit if any fixes needed**

Fix any type checker or linter issues discovered, then commit.
