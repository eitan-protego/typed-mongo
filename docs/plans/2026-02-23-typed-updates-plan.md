# Typed Update Operators Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add type-safe MongoDB update operators (`$set`, `$unset`, `$inc`, `$mul`, `$min`, `$max`, `$push`, `$pull`, `$addToSet`, `$pop`) and typed aggregation pipeline stages to the typed-mongo codegen system.

**Architecture:** Generate per-model TypedDicts for field categories (NumericFields, ArrayElementFields, etc.) and compose them into a unified `{Model}Update` TypedDict. Pipeline stages get their own typed dicts. The `TypedCollection` class gains an `Update` type parameter and typed `update_one`/`update_many` methods.

**Tech Stack:** Python 3.12+, Pydantic 2.0+, pymongo, basedpyright for type checking, pytest for testing.

**Test runner:** `uv run pytest` from the workspace root runs all tests. For specific tests: `uv run pytest typed_mongo/tests/test_operators.py -v` or `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`.

**Design doc:** `docs/plans/2026-02-23-typed-updates-design.md`

---

### Task 1: Add AggExprOp to operators.py

**Files:**
- Modify: `typed_mongo/src/typed_mongo/operators.py:48-52` (after the Op definition)
- Modify: `typed_mongo/src/typed_mongo/__init__.py` (export AggExprOp)
- Test: `typed_mongo/tests/test_operators.py`

**Step 1: Write the failing test**

Add to `typed_mongo/tests/test_operators.py`:

```python
from typed_mongo.operators import AggExprOp

def test_agg_expr_op_accepts_known_operators():
    """AggExprOp should accept known aggregation expression operator names."""
    op: AggExprOp = "$add"
    assert op == "$add"

    op2: AggExprOp = "$concat"
    assert op2 == "$concat"

    op3: AggExprOp = "$cond"
    assert op3 == "$cond"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo/tests/test_operators.py::test_agg_expr_op_accepts_known_operators -v`
Expected: FAIL with `ImportError: cannot import name 'AggExprOp'`

**Step 3: Write minimal implementation**

Add to end of `typed_mongo/src/typed_mongo/operators.py` (before `combine_ops`):

```python
# --- Aggregation expression operators (for pipeline updates) ---

type AggExprOp = Literal[
    "$add", "$subtract", "$multiply", "$divide", "$mod",
    "$concat", "$substr", "$toLower", "$toUpper", "$trim",
    "$cond", "$ifNull", "$switch",
    "$arrayElemAt", "$first", "$last", "$size", "$filter", "$map",
    "$mergeObjects", "$objectToArray", "$arrayToObject",
    "$toString", "$toInt", "$toDouble", "$toBool",
    "$type", "$literal",
    "$dateToString", "$dateFromString",
    "$abs", "$ceil", "$floor", "$round",
    "$max", "$min", "$avg", "$sum",
    "$and", "$or", "$not",
    "$eq", "$ne", "$gt", "$gte", "$lt", "$lte",
    "$in", "$setUnion", "$setIntersection",
]
```

Add to `typed_mongo/src/typed_mongo/__init__.py` imports and `__all__`:

```python
from typed_mongo.operators import AggExprOp
# Add "AggExprOp" to __all__
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest typed_mongo/tests/test_operators.py::test_agg_expr_op_accepts_known_operators -v`
Expected: PASS

**Step 5: Commit**

```bash
git add typed_mongo/src/typed_mongo/operators.py typed_mongo/src/typed_mongo/__init__.py typed_mongo/tests/test_operators.py
git commit -m "feat: add AggExprOp literal type for aggregation expression operators"
```

---

### Task 2: Add field categorization helpers to introspect.py

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/introspect.py:144` (append new functions)
- Test: `typed_mongo_gen/tests/test_field_path_collection.py`

**Step 1: Write the failing tests**

Add to `typed_mongo_gen/tests/test_field_path_collection.py`:

```python
from typed_mongo_gen.introspect import is_numeric_type, extract_list_element_type


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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_field_path_collection.py::test_is_numeric_type_int -v`
Expected: FAIL with `ImportError: cannot import name 'is_numeric_type'`

**Step 3: Write minimal implementation**

Append to `typed_mongo_gen/src/typed_mongo_gen/introspect.py`:

```python
def is_numeric_type(annotation: Any) -> bool:
    """Check if annotation is or contains a numeric type (int or float).

    Unwraps Optional, Annotated, TypeAliasType, and unions. Returns True
    if any non-None member is int or float. Returns False for list[int]
    (that's an array field, not a numeric field).
    """
    if isinstance(annotation, typing.TypeAliasType):
        return is_numeric_type(annotation.__value__)

    origin = get_origin(annotation)

    if origin is typing.Annotated:
        return is_numeric_type(get_args(annotation)[0])

    # list[X] is an array field, not numeric
    if origin is list:
        return False

    # Union: check if any non-None member is numeric
    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        return any(
            is_numeric_type(arg)
            for arg in get_args(annotation)
            if arg is not type(None)
        )

    return annotation is int or annotation is float


def extract_list_element_type(annotation: Any) -> Any | None:
    """Extract element type T from list[T], or None if not a list type.

    Unwraps Optional (list[T] | None -> T), Annotated, TypeAliasType.
    """
    if isinstance(annotation, typing.TypeAliasType):
        return extract_list_element_type(annotation.__value__)

    origin = get_origin(annotation)

    if origin is typing.Annotated:
        return extract_list_element_type(get_args(annotation)[0])

    # Union: find the list member (e.g. list[str] | None)
    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            result = extract_list_element_type(arg)
            if result is not None:
                return result
        return None

    if origin is list:
        args = get_args(annotation)
        if args:
            return args[0]
        return None

    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest typed_mongo_gen/tests/test_field_path_collection.py -k "numeric or extract_list" -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/introspect.py typed_mongo_gen/tests/test_field_path_collection.py
git commit -m "feat: add is_numeric_type and extract_list_element_type helpers"
```

---

### Task 3: Generate NumericFields and ArrayElementFields TypedDicts

This is the core codegen task. We modify `_write_model` in `codegen.py` to emit the new TypedDicts in the `.pyi` stub and simple `dict[str, Any]` aliases in the `.py` runtime file.

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py:250-307` (`_write_model` function)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

**Step 1: Write the failing tests**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
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
    assert '"age": int | float,' in content
    assert '"score": int | float,' in content
    # name, tags, active should NOT be in NumericFields
    assert '"name": int' not in content.split("MixedNumericFields")[1].split("total=False)")[0]
    assert '"tags": int' not in content.split("MixedNumericFields")[1].split("total=False)")[0]


def test_array_element_fields_typed_dict(tmp_path: Path):
    """Stub should have ArrayElementFields with only list fields, mapped to element type."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedArrayElementFields = TypedDict("MixedArrayElementFields"' in content
    # tags: list[str] -> element type str
    array_section = content.split("MixedArrayElementFields")[1].split("total=False)")[0]
    assert '"tags": str,' in array_section


def test_array_pop_fields_typed_dict(tmp_path: Path):
    """Stub should have ArrayPopFields with list fields mapped to Literal[1, -1]."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedArrayPopFields = TypedDict("MixedArrayPopFields"' in content
    pop_section = content.split("MixedArrayPopFields")[1].split("total=False)")[0]
    assert '"tags": Literal[1, -1],' in pop_section


def test_unset_fields_typed_dict(tmp_path: Path):
    """Stub should have UnsetFields with all fields mapped to Literal['']."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert 'MixedUnsetFields = TypedDict("MixedUnsetFields"' in content
    unset_section = content.split("MixedUnsetFields")[1].split("total=False)")[0]
    assert "\"name\": Literal['']," in unset_section
    assert "\"age\": Literal['']," in unset_section
    assert "\"score\": Literal['']," in unset_section
    assert "\"tags\": Literal['']," in unset_section
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_numeric_fields_typed_dict -v`
Expected: FAIL (no `MixedNumericFields` in output)

**Step 3: Write the implementation**

Modify `_write_model` in `typed_mongo_gen/src/typed_mongo_gen/codegen.py`. After the existing Fields TypedDict generation (line ~296), add generation of the new TypedDicts. Also add the necessary imports at the top of the function for `is_numeric_type` and `extract_list_element_type`.

Update the import at the top of codegen.py:

```python
from typed_mongo_gen.introspect import (
    collect_field_path_types,
    collect_field_paths,
    extract_list_element_type,
    is_numeric_type,
)
```

In `_write_model`, after the Fields TypedDict block (after line ~296), add:

```python
    # NumericFields TypedDict (only int/float fields)
    numeric_paths = {p: t for p, t in path_types.items() if is_numeric_type(t)}
    if numeric_paths:
        stub_f.write(f'{model_name}NumericFields = TypedDict("{model_name}NumericFields", {{\n')
        for path in sorted(numeric_paths):
            stub_f.write(f'    "{path}": int | float,\n')
        stub_f.write("}, total=False)\n\n")
    else:
        stub_f.write(f'{model_name}NumericFields = TypedDict("{model_name}NumericFields", {{}}, total=False)\n\n')

    # ArrayElementFields TypedDict (only list fields -> element type)
    array_paths: dict[str, str] = {}
    for p, t in path_types.items():
        elem = extract_list_element_type(t)
        if elem is not None:
            array_paths[p] = _annotation_to_source(elem, module_aliases)
    if array_paths:
        stub_f.write(f'{model_name}ArrayElementFields = TypedDict("{model_name}ArrayElementFields", {{\n')
        for path in sorted(array_paths):
            stub_f.write(f'    "{path}": {array_paths[path]},\n')
        stub_f.write("}, total=False)\n\n")
    else:
        stub_f.write(f'{model_name}ArrayElementFields = TypedDict("{model_name}ArrayElementFields", {{}}, total=False)\n\n')

    # ArrayPopFields TypedDict (only list fields -> Literal[1, -1])
    array_field_paths = sorted(array_paths.keys())
    if array_field_paths:
        stub_f.write(f'{model_name}ArrayPopFields = TypedDict("{model_name}ArrayPopFields", {{\n')
        for path in array_field_paths:
            stub_f.write(f'    "{path}": Literal[1, -1],\n')
        stub_f.write("}, total=False)\n\n")
    else:
        stub_f.write(f'{model_name}ArrayPopFields = TypedDict("{model_name}ArrayPopFields", {{}}, total=False)\n\n')

    # UnsetFields TypedDict (all fields -> Literal[""])
    stub_f.write(f'{model_name}UnsetFields = TypedDict("{model_name}UnsetFields", {{\n')
    for path in sorted(path_types):
        stub_f.write(f"    \"{path}\": Literal[''],\n")
    stub_f.write("}, total=False)\n\n")
```

Also add corresponding runtime aliases in the runtime file section (after `{model_name}Fields = dict[str, Any]\n`):

```python
    runtime_f.write(f"{model_name}NumericFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}ArrayElementFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}ArrayPopFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnsetFields = dict[str, Any]\n")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS (including existing tests)

**Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: generate NumericFields, ArrayElementFields, ArrayPopFields, UnsetFields TypedDicts"
```

---

### Task 4: Generate RefPath, PipelineSetFields, Update, and PipelineStage types

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py` (`_write_model` and `_write_headers`)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

**Step 1: Write the failing tests**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
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
    update_section = content.split("MixedUpdate = TypedDict")[1].split("total=False)")[0]
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
    ps_section = content.split("MixedPipelineSetFields")[1].split("total=False)")[0]
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


def test_generated_update_code_compiles(tmp_path: Path):
    """Generated stub with all update types should compile."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    stub_content = stub_path.read_text()
    compile(stub_content, "<test>", "exec")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_ref_path_literal_type -v`
Expected: FAIL

**Step 3: Write the implementation**

In `_write_headers` (the stub header section), add the AggExprOp import:

```python
    stub_f.write("from typed_mongo.operators import AggExprOp, Op\n")
```

(Change the existing line `from typed_mongo.operators import Op` to include `AggExprOp`.)

Also add `Mapping` import to stub headers. In `_write_headers`, after the typing imports line, ensure `Mapping` is imported:

```python
    stub_f.write("from collections.abc import Mapping\n")
```

In `_write_model`, after the UnsetFields TypedDict block from Task 3, add:

```python
    # RefPath: $-prefixed field paths for pipeline expressions
    stub_f.write(f"type {model_name}RefPath = Literal[\n")
    for path in paths:
        stub_f.write(f'    "${path}",\n')
    stub_f.write("]\n\n")

    # PipelineSetFields TypedDict (T | RefPath | Mapping[AggExprOp, Any])
    stub_f.write(f'{model_name}PipelineSetFields = TypedDict("{model_name}PipelineSetFields", {{\n')
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path], module_aliases)
        stub_f.write(f'    "{path}": {type_src} | {model_name}RefPath | Mapping[AggExprOp, Any],\n')
    stub_f.write("}, total=False)\n\n")

    # Update TypedDict (unified update document)
    stub_f.write(f'{model_name}Update = TypedDict("{model_name}Update", {{\n')
    stub_f.write(f'    "$set": {model_name}Fields,\n')
    stub_f.write(f'    "$unset": {model_name}UnsetFields,\n')
    stub_f.write(f'    "$inc": {model_name}NumericFields,\n')
    stub_f.write(f'    "$mul": {model_name}NumericFields,\n')
    stub_f.write(f'    "$min": {model_name}Fields,\n')
    stub_f.write(f'    "$max": {model_name}Fields,\n')
    stub_f.write(f'    "$push": {model_name}ArrayElementFields,\n')
    stub_f.write(f'    "$pull": {model_name}ArrayElementFields,\n')
    stub_f.write(f'    "$addToSet": {model_name}ArrayElementFields,\n')
    stub_f.write(f'    "$pop": {model_name}ArrayPopFields,\n')
    stub_f.write("}, total=False)\n\n")

    # Pipeline stage types
    stub_f.write(f'{model_name}PipelineSet = TypedDict("{model_name}PipelineSet", {{\n')
    stub_f.write(f'    "$set": {model_name}PipelineSetFields,\n')
    stub_f.write("})\n\n")

    stub_f.write(f'{model_name}PipelineUnset = TypedDict("{model_name}PipelineUnset", {{\n')
    stub_f.write(f'    "$unset": {model_name}Path | list[{model_name}Path],\n')
    stub_f.write("})\n\n")

    stub_f.write(f"type {model_name}PipelineStage = {model_name}PipelineSet | {model_name}PipelineUnset\n\n")
```

Also add runtime aliases for the new types:

```python
    runtime_f.write(f"type {model_name}RefPath = str\n")
    runtime_f.write(f"{model_name}PipelineSetFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Update = dict[str, Any]\n")
    runtime_f.write(f"{model_name}PipelineSet = dict[str, Any]\n")
    runtime_f.write(f"{model_name}PipelineUnset = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}PipelineStage = dict[str, Any]\n")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: generate RefPath, PipelineSetFields, Update, and PipelineStage types"
```

---

### Task 5: Update TypedCollection — rename type params, type update methods, remove set_fields

**Files:**
- Modify: `typed_mongo/src/typed_mongo/collection.py`
- Modify: `typed_mongo/src/typed_mongo/__init__.py` (no change needed unless exports change)
- Test: `typed_mongo/tests/test_operators.py` (add basic collection type param test)

**Step 1: Write the failing test**

Add to `typed_mongo/tests/test_operators.py`:

```python
from typed_mongo.collection import TypedCollection

def test_typed_collection_has_five_type_params():
    """TypedCollection should accept M, Path, Query, Fields, Update params."""
    # This is a compile-time check; at runtime just verify the class exists
    # and has the expected type parameter count
    params = TypedCollection.__type_params__
    assert len(params) == 5
    assert params[0].__name__ == "M"
    assert params[1].__name__ == "Path"
    assert params[2].__name__ == "Query"
    assert params[3].__name__ == "Fields"
    assert params[4].__name__ == "Update"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo/tests/test_operators.py::test_typed_collection_has_five_type_params -v`
Expected: FAIL (currently 4 params named M, P, Q, F)

**Step 3: Write the implementation**

Replace the TypedCollection class definition in `typed_mongo/src/typed_mongo/collection.py`. Key changes:

1. Rename type params: `M, P, Q, F` → `M, Path, Query, Fields, Update`
2. Add `Update` type param (bound to `Mapping[str, Any]`)
3. Type `update_one` to use `Update` instead of `dict[str, Any]`
4. Add `update_many` method
5. Remove `set_fields` method
6. Update docstring and `from_database` return type

Replace the class (lines 70-226) with:

```python
class TypedCollection[
    M: MongoCollectionModel,
    Path: str,
    Query: Mapping[str, Any],
    Fields: Mapping[str, Any],
    Update: Mapping[str, Any],
]:
    """Type-safe wrapper around ``AsyncCollection``.

    Method signatures use generated types (M, Path, Query, Fields, Update)
    instead of ``dict[str, Any]``, so that field path typos and wrong
    update value types are caught at type-check time.

    Type parameters:
        M: MongoCollectionModel subclass
        Path: Literal path type (e.g. ``UserPath``) for single-field args
        Query: Query TypedDict (e.g. ``UserQuery``) for filter args
        Fields: Fields TypedDict (e.g. ``UserFields``) for $set value args
        Update: Update TypedDict (e.g. ``UserUpdate``) for update documents
    """

    def __init__(
        self,
        model: type[M],
        collection: AsyncCollection[dict[str, Any]],
    ) -> None:
        self._model: type[M] = model
        self._collection: AsyncCollection[dict[str, Any]] = collection

    @classmethod
    def from_database(
        cls, model: type[M], db: AsyncDatabase[dict[str, Any]]
    ) -> TypedCollection[M, Any, Any, Any, Any]:
        """Factory: create a TypedCollection from a database and model class."""
        collection = model.get_collection(db)
        return cls(model, collection)

    # --- Read operations ---

    async def find_one(self, filter: Query) -> M | None:  # noqa: A002
        """Find a single document matching the filter."""
        doc = await self._collection.find_one(filter)
        if doc is None:
            return None
        return self._model.model_validate(doc)

    def find(self, filter: Query | None = None) -> TypedCursor[M]:  # noqa: A002
        """Find documents matching the filter."""
        cursor = self._collection.find(filter)
        return TypedCursor(self._model, cursor)

    async def count_documents(self, filter: Query) -> int:  # noqa: A002
        """Count documents matching the filter."""
        return await self._collection.count_documents(filter)

    async def distinct(  # noqa: A002
        self, key: Path, filter: Query | None = None
    ) -> list[Any]:
        """Get distinct values for a field."""
        return await self._collection.distinct(key, filter=filter)

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> list[M]:
        """Run an aggregation pipeline and validate results as models."""
        cursor = await self._collection.aggregate(pipeline)
        docs = await cursor.to_list()
        return [self._model.model_validate(doc) for doc in docs]

    # --- Write operations ---

    async def insert_one(self, document: M) -> InsertOneResult:
        """Insert a document, serialized via ``model_dump()``."""
        doc = document.model_dump()
        return await self._collection.insert_one(doc)

    async def replace_one(
        self,
        filter: Query,
        replacement: M,
        upsert: bool = False,
    ) -> UpdateResult:
        """Replace a document, serialized via ``model_dump()``."""
        doc = replacement.model_dump()
        return await self._collection.replace_one(filter, doc, upsert=upsert)

    async def update_one(
        self,
        filter: Query,  # noqa: A002
        update: Update,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """Type-safe update of a single document."""
        return await self._collection.update_one(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def update_many(
        self,
        filter: Query,  # noqa: A002
        update: Update,
        upsert: bool = False,
        array_filters: list[dict[str, Any]] | None = None,
    ) -> UpdateResult:
        """Type-safe update of multiple documents."""
        return await self._collection.update_many(
            filter, update, upsert=upsert, array_filters=array_filters
        )

    async def delete_one(self, filter: Query) -> DeleteResult:  # noqa: A002
        """Delete a single document matching the filter."""
        return await self._collection.delete_one(filter)

    # --- Escape hatch ---

    @property
    def raw(self) -> AsyncCollection[dict[str, Any]]:
        """Access the underlying ``AsyncCollection`` directly."""
        return self._collection
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest typed_mongo/tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add typed_mongo/src/typed_mongo/collection.py typed_mongo/tests/test_operators.py
git commit -m "feat: add Update type param to TypedCollection, type update_one/update_many, remove set_fields"
```

---

### Task 6: Update codegen to emit 5-param Collection stubs

**Files:**
- Modify: `typed_mongo_gen/src/typed_mongo_gen/codegen.py` (`_write_model` Collection class section)
- Test: `typed_mongo_gen/tests/test_code_generation.py`

**Step 1: Write the failing test**

Add to `typed_mongo_gen/tests/test_code_generation.py`:

```python
def test_collection_stub_has_five_type_params(tmp_path: Path):
    """Generated Collection stub should use all 5 type params including Update."""
    runtime_path = tmp_path / "out.py"
    stub_path = tmp_path / "out.pyi"
    write_field_paths(runtime_path, stub_path, {"Mixed": _ModelWithMixedFields})

    content = stub_path.read_text()
    assert (
        "class MixedCollection("
        "TypedCollection[_ModelWithMixedFields, MixedPath, MixedQuery, MixedFields, MixedUpdate]"
        "):" in content
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest typed_mongo_gen/tests/test_code_generation.py::test_collection_stub_has_five_type_params -v`
Expected: FAIL (currently only 4 params)

**Step 3: Write the implementation**

In `_write_model` in codegen.py, update the Collection class stub generation (currently around lines 298-307). Change the TypedCollection type params to include the Update type:

Replace:
```python
    stub_f.write(
        f"class {model_name}Collection("
        + f"TypedCollection[{model_ref}, {model_name}Path, {model_name}Query, {model_name}Fields]"
        + "):\n"
    )
```

With:
```python
    stub_f.write(
        f"class {model_name}Collection("
        + f"TypedCollection[{model_ref}, {model_name}Path, {model_name}Query, {model_name}Fields, {model_name}Update]"
        + "):\n"
    )
```

**Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add typed_mongo_gen/src/typed_mongo_gen/codegen.py typed_mongo_gen/tests/test_code_generation.py
git commit -m "feat: emit 5-param Collection stub with Update type"
```

---

### Task 7: Update integration tests and verify end-to-end

**Files:**
- Modify: `typed_mongo_gen/tests/test_integration.py`
- Modify: `typed_mongo/examples/basic_usage.py` (if it references set_fields)

**Step 1: Write/update integration test**

Update `test_end_to_end_generation` in `typed_mongo_gen/tests/test_integration.py` to also verify the new update types are generated. Add assertions after the existing ones:

```python
    # Verify update types are generated
    assert 'ProductUpdate = TypedDict("ProductUpdate"' in stub_content
    assert 'ProductNumericFields = TypedDict("ProductNumericFields"' in stub_content
    assert "type ProductRefPath = Literal[" in stub_content
    assert '"$price",' in stub_content  # RefPath should have $-prefixed paths
    assert '"$set": ProductFields,' in stub_content
    assert '"$inc": ProductNumericFields,' in stub_content
    assert "type ProductPipelineStage = " in stub_content
```

Also update the runtime content assertions to include new aliases:

```python
    assert "ProductUpdate = dict[str, Any]" in runtime_content
    assert "ProductNumericFields = dict[str, Any]" in runtime_content
```

**Step 2: Run integration test to verify it passes**

Run: `uv run pytest typed_mongo_gen/tests/test_integration.py -v`
Expected: All PASS

**Step 3: Check and update examples if needed**

Read `typed_mongo/examples/basic_usage.py` — if it uses `set_fields`, update to use `update_one(filter, {"$set": fields})` instead.

**Step 4: Run the full test suite**

Run: `uv run pytest -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add typed_mongo_gen/tests/test_integration.py
git commit -m "test: update integration tests for typed update operators"
```

---

### Task 8: Final verification — lint, type check, all tests green

**Step 1: Run linter**

Run: `uv run ruff check .`
Expected: No errors

**Step 2: Run type checker**

Run: `uv run basedpyright`
Expected: No errors (or only pre-existing ones)

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

**Step 4: Fix any issues found, then commit**

If there are lint/type issues, fix them and commit with an appropriate message.
