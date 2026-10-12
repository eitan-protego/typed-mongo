# typed_mongo

Type-safe MongoDB operators, collection models, and aggregation pipeline types.

## Installation

```bash
pip install typed-mongo
```

## MongoCollectionModel

Base class for MongoDB-backed Pydantic models. Subclasses that define `__collection_name__` are discovered by the code generator.

```python
from typed_mongo import MongoCollectionModel

class User(MongoCollectionModel):
    __collection_name__ = "users"
    name: str
    email: str
    age: int | None = None
```

Inherits Pydantic `BaseModel` with `serialize_by_alias=True` and `validate_by_alias=True`.

## TypedCollection

Wraps pymongo's `AsyncCollection` with typed method signatures. The code generator produces a concrete subclass per model (e.g. `UserCollection`) with all type parameters filled in.

```python
from app._generated_types import UserCollection

users = UserCollection(db)
await users.find_one({"name": "Alice"})
await users.update_one({"name": "Alice"}, {"$set": {"age": 30}})
await users.insert_one(User(name="Bob", email="bob@example.com"))
```

## Aggregation pipelines

`aggregate()` accepts type-safe pipeline stages. Shape-preserving stages (search, match, sort, limit, skip, set, addFields, unset) return `TypedCursor[M]`. An optional `type_unsafe_pipeline_suffix` for shape-changing stages (group, unwind, project, lookup, bucket) returns `AsyncCursor[dict[str, Any]]`.

```python
# Safe pipeline — returns typed cursor
async for user in await users.aggregate([
    {"$match": {"age": {"$gt": 18}}},
    {"$sort": {"name": 1}},
]):
    print(user.name)

# Unsafe suffix — returns untyped cursor
from app._generated_types import user_aggregation_step
results = await users.aggregate(
    [{"$match": {"age": {"$gt": 18}}}],
    type_unsafe_pipeline_suffix=[
        user_aggregation_step({"$group": {"_id": "$age"}}),
    ],
)
```

## Operators

### Atlas Search

Enable the collection's search types in your codegen job and regenerate to use `$search` in typed pipelines:

```toml
[[tool.typed-mongo-gen.jobs]]
sources = ["app/models/**/*.py"]
output = "app/_generated_types.py"
searchable_collections = ["users"]
```

Search generation is disabled by default. Collection names are matched against `__collection_name__`, independent of the model class name.

```python
async for user in await users.aggregate([
    {"$search": {
        "index": "users",
        "compound": {
            "must": [{"text": {"path": "name", "query": "Alice"}}],
            "filter": [{"range": {"path": "age", "gte": 18}}],
        },
    }},
    {"$limit": 10},
]):
    print(user.name)
```

Generated `UserSearchStage` and `UserSearchOptions` check model field paths (including serialized aliases), required operator fields, and common options. Text, autocomplete, phrase, regex, wildcard, queryString, equals, in, exists, range, near, compound, and embeddedDocument have typed payloads. Wildcard path expressions and multi-analyzer paths are supported. Scoring, geometry, and other advanced operator payloads remain open dictionaries; equality values and range bounds are not checked against model field types.

MongoDB requires `$search` to be the first stage; stage ordering, index configuration, and mutually exclusive options are validated by MongoDB, rather than these types. See the [MongoDB `$search` reference](https://www.mongodb.com/docs/search/query/aggregation-stages/search/).

`returnStoredSource=True` and `returnScope` can change the result shape, so use the untyped `SearchStage` from `typed_mongo.operators` in an unsafe pipeline suffix for those options.

`UserSearchMetaStage` checks metadata queries too. Pass it through `user_aggregation_step()` in an unsafe suffix, starting with an empty safe pipeline when `$searchMeta` is the first stage:

```python
results = await users.aggregate([], [
    user_aggregation_step({"$searchMeta": {
        "text": {"path": "name", "query": "Alice"},
        "count": {"type": "total"},
    }}),
])
```

`UserSearchMetaOptions` follows the [metadata stage syntax](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/), including scoped results, and excludes document-only options such as sorting and highlighting.

Field-only sorts accept typed mappings of model paths to `1` or `-1`. For a mixed field and score sort, use `typed_mongo.search.combine_search_sort()` with an explicitly typed field mapping; score sorts can use arbitrary output names. This follows the same approach as `combine_ops()` while avoiding another copy of every field path in generated stubs.

### Query operators

`Op[T]` represents MongoDB query operators for a field of type `T`:

```python
from typed_mongo.operators import Op

query: Op[int] = {"$gt": 18, "$lt": 65}
query: Op[str] = {"$in": ["a", "b", "c"]}
```

`AggregationStep` is a union of all MongoDB aggregation stage TypedDicts, used as the base type for untyped pipeline stages.
