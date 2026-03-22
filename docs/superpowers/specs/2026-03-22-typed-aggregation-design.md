# Type-Safe Aggregation Pipeline Design

## Overview

Add type-safe aggregation pipeline support to typed-mongo. Each aggregation stage is a TypedDict. Codegen produces per-model stage types with field-level checking. The base library provides a structural `AggregationStep` type covering all MongoDB stages without model-specific validation. `TypedCollection.aggregate()` uses overloads to return `TypedCursor[M]` for safe-only pipelines and `AsyncCursor[dict[str, Any]]` when an unsafe suffix is present.

## Files Modified

- `typed_mongo/src/typed_mongo/operators.py` — add `AggregationStep` union type (runtime + type stub via inline conditional or the existing pattern of Mapping-based type aliases)
- `typed_mongo/src/typed_mongo/collection.py` — add 7th type parameter `PipelineStage` to `TypedCollection`, rewrite `aggregate()` with two overloads
- `typed_mongo_gen/src/typed_mongo_gen/codegen.py` — generate per-model aggregation stage TypedDicts, `{name}_aggregation_step()` helper, and updated `Collection` class

No new files.

## Base Library Changes

### `operators.py`: `AggregationStep`

A union of TypedDicts covering all MongoDB aggregation stages. Stages that have model-specific codegen helpers get structural validation (required keys checked). Remaining stages get minimal annotations.

**Structurally validated stages** (these also get model-specific codegen helpers):

| Stage | Base validation |
|---|---|
| `$group` | Requires `_id` key, value `dict[str, Any]` |
| `$bucket` | Requires `groupBy`, `boundaries`, `default`, optional `output` |
| `$bucketAuto` | Requires `groupBy`, `buckets` |
| `$unwind` | Value is `str` or `dict` with required `path` |
| `$project` | Value is `dict[str, Any]` |
| `$lookup` | Requires `from`, `localField`, `foreignField`, `as` |

**Minimally annotated stages** (shape-only, no model-specific helpers):

| Stage | Base type |
|---|---|
| `$match` | `dict[str, Any]` |
| `$sort` | `dict[str, int]` |
| `$limit` | `int` |
| `$skip` | `int` |
| `$set` / `$addFields` | `dict[str, Any]` |
| `$unset` | `str \| list[str]` |
| `$count` | `str` |
| `$replaceRoot` | `dict[str, Any]` |
| `$replaceWith` | `dict[str, Any]` |
| `$out` | `str \| dict[str, Any]` |
| `$merge` | `str \| dict[str, Any]` |
| `$facet` | `dict[str, list[Any]]` |
| `$graphLookup` | `dict[str, Any]` |
| `$redact` | `dict[str, Any]` |
| `$sample` | `dict[str, int]` |
| `$unionWith` | `str \| dict[str, Any]` |
| `$sortByCount` | `str \| dict[str, Any]` |
| `$geoNear` | `dict[str, Any]` |
| `$densify` | `dict[str, Any]` |
| `$fill` | `dict[str, Any]` |
| `$documents` | `list[dict[str, Any]]` |
| `$setWindowFields` | `dict[str, Any]` |
| `$changeStream` | `dict[str, Any]` |
| `$collStats` | `dict[str, Any]` |
| `$currentOp` | `dict[str, Any]` |
| `$indexStats` | `dict[str, Any]` |
| `$listSessions` | `dict[str, Any]` |
| `$planCacheStats` | `dict[str, Any]` |
| `$search` | `dict[str, Any]` |
| `$searchMeta` | `dict[str, Any]` |

Each stage is a closed TypedDict with a single `$`-prefixed key. `AggregationStep` is the union of all of them.

Runtime definition: `type AggregationStep = dict[str, Any]` (no runtime cost).

Type stub (in `operators.py` itself, using `TYPE_CHECKING` guard or maintaining the existing pattern of using Mapping-based type aliases that work both at runtime and for type checkers — whichever is simpler given that operators.py currently has no `.pyi`): full TypedDict definitions.

Since `operators.py` currently has no separate `.pyi`, and adding a new file is not allowed, these TypedDict definitions will be written directly in `operators.py`. They impose no meaningful runtime cost since TypedDict classes are lightweight. The runtime `type AggregationStep = dict[str, Any]` alias will be used in the generated runtime `.py`, while the stub `.pyi` will import and use the real union type.

### `collection.py`: 7th Type Parameter + Overloaded `aggregate()`

Add `PipelineStage: Mapping[str, Any]` as the 7th type parameter:

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

Overloaded `aggregate()`:

```python
from typing import overload

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
    full_pipeline: list[dict[str, Any]] = list(pipeline)  # type: ignore
    if type_unsafe_pipeline_suffix:
        full_pipeline.extend(type_unsafe_pipeline_suffix)  # type: ignore
        return self._collection.aggregate(full_pipeline)
    return TypedCursor(self._model, self._collection.aggregate(full_pipeline))
```

`from_database` return type annotation updated to include 7th `Any`.

## Codegen Changes

### New Per-Model Types (stub `.pyi` only)

For a model named `User`:

#### 1. Type-safe RefPaths grouped by value type

Replace the single `UserRefPath` with per-type ref paths:

```python
type UserStrRefPath = Literal["$name", "$email"]
type UserIntRefPath = Literal["$age"]
type UserFloatRefPath = Literal["$score"]
# etc. for each distinct field value type
```

The existing `UserRefPath` (union of all `$`-prefixed paths) is kept for use in unsafe helpers. The per-type variants are new and used in `PipelineSetFields`.

#### 2. Updated `PipelineSetFields` with type-safe refs and `extra_items`

```python
UserPipelineSetFields = TypedDict("UserPipelineSetFields", {
    "name": str | UserStrRefPath | Mapping[AggExprOp, Any],
    "email": str | UserStrRefPath | Mapping[AggExprOp, Any],
    "age": int | None | UserIntRefPath | Mapping[AggExprOp, Any],
    "score": float | UserFloatRefPath | Mapping[AggExprOp, Any],
}, total=False, closed=True, extra_items=Any)
```

Uses `typing_extensions.TypedDict` with PEP 728 `extra_items=Any` so arbitrary new field names are accepted (Pydantic ignores them). `closed=True` on known fields ensures they're type-checked.

#### 3. `OptionalPath` — fields with defaults

```python
type UserOptionalPath = Literal["nickname", "bio"]  # only fields with defaults
```

Determined during introspection: a field has a default if `field_info.default is not PydanticUndefined` or `field_info.default_factory is not None`.

#### 4. Safe aggregation stage TypedDicts

All use `closed=True` and function-call syntax (for `$`-prefixed keys):

```python
UserMatchStage = TypedDict("UserMatchStage", {
    "$match": UserQuery,
}, closed=True)

UserSortStage = TypedDict("UserSortStage", {
    "$sort": dict[UserPath, Literal[1, -1]],
}, closed=True)

UserLimitStage = TypedDict("UserLimitStage", {
    "$limit": int,
}, closed=True)

UserSkipStage = TypedDict("UserSkipStage", {
    "$skip": int,
}, closed=True)

UserSetStage = TypedDict("UserSetStage", {
    "$set": UserPipelineSetFields,
}, closed=True)

UserAddFieldsStage = TypedDict("UserAddFieldsStage", {
    "$addFields": UserPipelineSetFields,
}, closed=True)

UserAggUnsetStage = TypedDict("UserAggUnsetStage", {
    "$unset": UserOptionalPath | list[UserOptionalPath],
}, closed=True)
```

Note: `UserAggUnsetStage` (named to avoid collision with existing `UserPipelineUnset`) only allows unsetting fields with defaults.

#### 5. `PipelineStage` union

```python
type UserPipelineStage = (
    UserMatchStage | UserSortStage | UserLimitStage | UserSkipStage
    | UserSetStage | UserAddFieldsStage | UserAggUnsetStage
)
```

#### 6. Model-specific unsafe stage helpers

TypedDicts for stages that check field references in their inputs but produce unknowable output shapes:

```python
# $group — _id checked against RefPath (simple cases)
UserGroupStage = TypedDict("UserGroupStage", {
    "$group": UserGroupFields,
}, closed=True)

class UserGroupFields(TypedDict, total=False, closed=True):
    _id: UserRefPath | list[UserRefPath] | dict[str, UserRefPath] | None

# $unwind — path checked against RefPath
UserUnwindStage = TypedDict("UserUnwindStage", {
    "$unwind": UserRefPath,
}, closed=True)

# $project — field names checked against Path
UserProjectStage = TypedDict("UserProjectStage", {
    "$project": dict[UserPath, Literal[0, 1] | dict[str, Any]],
}, closed=True)

# $bucket — groupBy checked against RefPath
UserBucketStage = TypedDict("UserBucketStage", {
    "$bucket": UserBucketFields,
}, closed=True)

class UserBucketFields(TypedDict, closed=True):
    groupBy: UserRefPath
    boundaries: list[Any]
    default: Any
    output: dict[str, Any]  # total=False not applicable to individual keys here

# $bucketAuto — groupBy checked against RefPath
UserBucketAutoStage = TypedDict("UserBucketAutoStage", {
    "$bucketAuto": UserBucketAutoFields,
}, closed=True)

class UserBucketAutoFields(TypedDict, closed=True):
    groupBy: UserRefPath
    buckets: int

# $lookup — localField checked against Path
UserLookupStage = TypedDict("UserLookupStage", {
    "$lookup": UserLookupFields,
}, closed=True)

# Uses function-call syntax due to "from" being a Python keyword
UserLookupFields = TypedDict("UserLookupFields", {
    "from": str,
    "localField": UserPath,
    "foreignField": str,
    "as": str,
}, closed=True)
```

#### 7. `{name}_aggregation_step()` function

```python
# Runtime .py
def user_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:
    return step

# Stub .pyi
type UserUnsafeStage = (
    UserGroupStage | UserUnwindStage | UserProjectStage
    | UserBucketStage | UserBucketAutoStage | UserLookupStage
)

def user_aggregation_step(step: UserUnsafeStage) -> AggregationStep: ...
```

Accepts the union of model-specific unsafe stages, returns `AggregationStep`. At runtime it's an identity function.

#### 8. Updated `Collection` class

```python
class UserCollection(
    TypedCollection[User, UserDict, UserPath, UserQuery, UserFields, UserUpdate, UserPipelineStage]
):
    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None: ...
```

### Runtime `.py` additions

Minimal aliases for all new types:

```python
type UserOptionalPath = str
UserMatchStage = dict[str, Any]
UserSortStage = dict[str, Any]
UserLimitStage = dict[str, Any]
UserSkipStage = dict[str, Any]
UserSetStage = dict[str, Any]
UserAddFieldsStage = dict[str, Any]
UserAggUnsetStage = dict[str, Any]
UserGroupStage = dict[str, Any]
UserGroupFields = dict[str, Any]
UserUnwindStage = dict[str, Any]
UserProjectStage = dict[str, Any]
UserBucketStage = dict[str, Any]
UserBucketFields = dict[str, Any]
UserBucketAutoStage = dict[str, Any]
UserBucketAutoFields = dict[str, Any]
UserLookupStage = dict[str, Any]
UserLookupFields = dict[str, Any]
type UserUnsafeStage = dict[str, Any]

def user_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:
    return step
```

## Usage Examples

```python
users = UserCollection(db)

# Safe-only pipeline — returns TypedCursor[User]
cursor = await users.aggregate([
    {"$match": {"age": {"$gt": 18}}},
    {"$sort": {"name": 1}},
    {"$set": {"email": "$backup_email"}},  # only str refs for str field
    {"$limit": 10},
])
async for user in cursor:
    print(user.name)  # fully typed as User

# With unsafe suffix — returns AsyncCursor[dict[str, Any]]
cursor = await users.aggregate(
    [{"$match": {"status": "active"}}],
    [user_aggregation_step({"$group": {"_id": "$department"}}),
     {"$sort": {"count": -1}}],
)
docs = await cursor.to_list()
# docs is list[dict[str, Any]]

# Using base library without codegen — basic shape checking only
from typed_mongo.operators import AggregationStep
raw_pipeline: list[AggregationStep] = [
    {"$group": {"_id": "$field"}},  # checked: $group requires _id
    {"$sort": {"count": -1}},
]
```

## Testing Strategy

- Unit tests for each generated stage TypedDict (verify correct fields, types, closed behavior)
- Unit tests for `{name}_aggregation_step()` function generation
- Unit tests for `AggregationStep` base types (structural validation)
- Integration tests verifying `TypedCollection.aggregate()` overload behavior (return types)
- Existing tests must continue to pass (7th type parameter is backward-compatible via `Any` default)
