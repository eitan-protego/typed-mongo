# Typed Update Operators Design

## Goal

Add type-safe MongoDB update operations to typed-mongo. Currently only `$set` is typed (via the now-removed `set_fields()` convenience method). This design adds typed support for all standard update operators and aggregation-style pipeline updates.

## Supported Operators

### Standard update operators

| Operator | Field set | Value type |
|----------|-----------|------------|
| `$set` | All fields (`Fields`) | Field's own type `T` |
| `$unset` | All fields (`UnsetFields`) | `Literal[""]` |
| `$inc` | Numeric fields only (`NumericFields`) | `int \| float` |
| `$mul` | Numeric fields only (`NumericFields`) | `int \| float` |
| `$min` | All fields (`Fields`) | Field's own type `T` |
| `$max` | All fields (`Fields`) | Field's own type `T` |
| `$push` | Array fields only (`ArrayElementFields`) | Element type `T` |
| `$pull` | Array fields only (`ArrayElementFields`) | Element type `T` |
| `$addToSet` | Array fields only (`ArrayElementFields`) | Element type `T` |
| `$pop` | Array fields only (`ArrayPopFields`) | `Literal[1, -1]` |

Excluded: `$rename` (hard to type correctly — both key and value are field paths with constraints), `$currentDate` (rarely used).

### Aggregation pipeline stages

Pipeline updates are passed as a list of stage dicts. Supported stages:

| Stage | Typing |
|-------|--------|
| `$set` / `$addFields` | Field names typed, values are `T \| RefPath \| Mapping[AggExprOp, Any]` |
| `$unset` | `Path \| list[Path]` |

Other pipeline stages (`$replaceRoot`, `$replaceWith`) are out of scope — they change the document shape and can't be typed against the original model.

## Generated Types

For a model like:

```python
class User(MongoCollectionModel):
    __collection_name__ = "users"
    name: str
    email: str
    age: int | None = None
    score: float = 0.0
    tags: list[str] = []
```

### Existing (unchanged)

```python
type UserPath = Literal["name", "email", "age", "score", "tags"]
UserQuery = TypedDict("UserQuery", {...}, total=False)
UserFields = TypedDict("UserFields", {
    "name": str, "email": str, "age": int | None, "score": float, "tags": list[str],
}, total=False)
```

### New types

```python
# $-prefixed field references for pipeline expressions
type UserRefPath = Literal["$name", "$email", "$age", "$score", "$tags"]

# Only int/float leaf types (Optional wrappers stripped)
UserNumericFields = TypedDict("UserNumericFields", {
    "age": int | float,
    "score": int | float,
}, total=False)

# Only list[T] fields -> element type T
UserArrayElementFields = TypedDict("UserArrayElementFields", {
    "tags": str,
}, total=False)

# Only list fields -> Literal[1, -1]
UserArrayPopFields = TypedDict("UserArrayPopFields", {
    "tags": Literal[1, -1],
}, total=False)

# All fields -> Literal[""]
UserUnsetFields = TypedDict("UserUnsetFields", {
    "name": Literal[""],
    "email": Literal[""],
    "age": Literal[""],
    "score": Literal[""],
    "tags": Literal[""],
}, total=False)

# Pipeline $set: field names typed, values are T | RefPath | expression
UserPipelineSetFields = TypedDict("UserPipelineSetFields", {
    "name": str | UserRefPath | Mapping[AggExprOp, Any],
    "email": str | UserRefPath | Mapping[AggExprOp, Any],
    "age": int | None | UserRefPath | Mapping[AggExprOp, Any],
    "score": float | UserRefPath | Mapping[AggExprOp, Any],
    "tags": list[str] | UserRefPath | Mapping[AggExprOp, Any],
}, total=False)

# Unified update document
UserUpdate = TypedDict("UserUpdate", {
    "$set": UserFields,
    "$unset": UserUnsetFields,
    "$inc": UserNumericFields,
    "$mul": UserNumericFields,
    "$min": UserFields,
    "$max": UserFields,
    "$push": UserArrayElementFields,
    "$pull": UserArrayElementFields,
    "$addToSet": UserArrayElementFields,
    "$pop": UserArrayPopFields,
}, total=False)

# Pipeline stages
UserPipelineSet = TypedDict("UserPipelineSet", {
    "$set": UserPipelineSetFields,
})
UserPipelineUnset = TypedDict("UserPipelineUnset", {
    "$unset": UserPath | list[UserPath],
})
type UserPipelineStage = UserPipelineSet | UserPipelineUnset
```

### Field categorization rules

A field is **numeric** if its leaf type (after unwrapping `Optional`, `Annotated`, `TypeAliasType`) is or contains `int` or `float`. For union types like `int | None`, the numeric type is extracted. NumericFields values are always `int | float`.

A field is an **array field** if its leaf type's origin is `list`. For `list[T]`, the element type `T` is used in `ArrayElementFields`. Nested dot-paths into list elements (e.g. `items.price`) are categorized by their own leaf type — so `items.price: float` appears in NumericFields.

## TypedCollection Changes

### Type parameter rename

```python
# Before
class TypedCollection[M, P, Q, F]: ...

# After
class TypedCollection[M, Path, Query, Fields, Update]: ...
```

### Method changes

- `update_one(filter, update, ...)` — `update` param typed as `Update` (was `dict[str, Any]`)
- `update_many(filter, update, ...)` — new method, typed same as `update_one`
- `set_fields()` — removed (not a pymongo method; users use `update_one(f, {"$set": fields})`)

Pipeline updates use the same `update_one`/`update_many` methods. The `update` param accepts `Update | list[PipelineStage]` in the generated stub.

### Generated collection stub

```python
class UserCollection(
    TypedCollection[User, UserPath, UserQuery, UserFields, UserUpdate]
):
    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None: ...
```

## operators.py Changes

Add `AggExprOp` — a `Literal` type of common aggregation expression operators:

```python
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

## introspect.py Changes

Add field categorization helpers:

- `is_numeric_type(annotation) -> bool` — checks if leaf type is int or float
- `extract_list_element_type(annotation) -> type | None` — returns element type T for list[T], None otherwise
- These are used by codegen to partition fields into NumericFields, ArrayElementFields, etc.

## File changes summary

| File | Change |
|------|--------|
| `typed_mongo/operators.py` | Add `AggExprOp` literal type |
| `typed_mongo/collection.py` | Rename type params; type `update_one`/`update_many`; add `update_many`; remove `set_fields` |
| `typed_mongo_gen/introspect.py` | Add `is_numeric_type()`, `extract_list_element_type()` |
| `typed_mongo_gen/codegen.py` | Generate new TypedDicts (NumericFields, ArrayElementFields, ArrayPopFields, UnsetFields, RefPath, PipelineSetFields, Update, PipelineStage) |
| Tests | Update existing tests for renamed params and removed `set_fields`; add tests for new generated types |
