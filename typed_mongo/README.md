# typed_mongo

Type-safe MongoDB operators, collection models, and aggregation pipeline types.

## Installation

```bash
pip install typed-mongo
```

## Usage

### Define models

```python
from typed_mongo import MongoCollectionModel

class User(MongoCollectionModel):
    __collection_name__ = "users"

    name: str
    email: str
    age: int | None = None
```

Models that define `__collection_name__` are discovered by the code generator. They inherit Pydantic's `BaseModel` with `serialize_by_alias=True` and `validate_by_alias=True` enabled by default.

### TypedCollection

`TypedCollection` wraps pymongo's `AsyncCollection` with typed method signatures. The code generator produces a concrete subclass per model (e.g. `UserCollection`) with all type parameters filled in.

```python
from app._generated_types import UserCollection

users = UserCollection(db)

# All methods are type-checked against generated types:
await users.find_one({"name": "Alice"})
await users.update_one({"name": "Alice"}, {"$set": {"age": 30}})
await users.insert_one(User(name="Bob", email="bob@example.com"))
```

### Aggregation pipelines

The `aggregate()` method accepts type-safe pipeline stages. Shape-preserving stages (match, sort, limit, skip, set, addFields, unset) return `TypedCursor[M]`. An optional `type_unsafe_pipeline_suffix` for shape-changing stages (group, unwind, project, lookup, bucket) returns `AsyncCursor[dict[str, Any]]`.

```python
# Safe pipeline — returns typed results
results = await users.aggregate([
    {"$match": {"age": {"$gt": 18}}},
    {"$sort": {"name": 1}},
    {"$limit": 10},
])

# Mixed pipeline — unsafe suffix returns untyped cursor
results = await users.aggregate(
    [{"$match": {"age": {"$gt": 18}}}],
    type_unsafe_pipeline_suffix=[
        user_aggregation_step({"$group": {"_id": "$age"}}),
    ],
)
```

### Operators

The `Op[T]` type represents MongoDB query operators for a field of type `T`:

```python
from typed_mongo.operators import Op

filter: Op[int] = {"$gt": 18, "$lt": 65}
filter: Op[str] = {"$regex": "^test", "$options": "i"}
filter: Op[str] = {"$in": ["a", "b", "c"]}
```

### AggregationStep

`AggregationStep` is a union of all MongoDB aggregation stage TypedDicts, used as the base type for untyped/unsafe pipeline stages.
