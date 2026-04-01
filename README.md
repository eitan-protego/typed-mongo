# Typed MongoDB

Type-safe MongoDB operations for Python using Pydantic model introspection.

## Packages

- **[typed_mongo](typed_mongo/README.md)**: Runtime package — operators, collection model base class, type-safe collection/cursor wrappers, aggregation stage types
- **[typed_mongo_gen](typed_mongo_gen/README.md)**: Code generator — introspects Pydantic models and emits `.py`/`.pyi` type definitions for queries, updates, and aggregation pipelines

## Quick Start

```bash
pip install typed-mongo typed-mongo-gen
```

Define a model, generate types, use them:

```python
from typed_mongo import MongoCollectionModel

class User(MongoCollectionModel):
    __collection_name__ = "users"
    name: str
    email: str
    age: int | None = None
```

```bash
typed-mongo-gen 'app/models/**/*.py' --output app/_generated_types.py
```

```python
from app._generated_types import UserCollection

users = UserCollection(db)
await users.find({"age": {"$gt": 18}})          # type-checked query
await users.update_one({"name": "Alice"}, {"$set": {"age": 30}})  # type-checked update
```

## Development

```bash
uv sync

# Run tests per package (avoids import collisions)
cd typed_mongo && uv run pytest
cd typed_mongo_gen && uv run pytest
```

## Requirements

- Python 3.12+
- Pydantic 2.0+
- pymongo/motor
