# Typed MongoDB

Type-safe MongoDB operations for Python using Pydantic model introspection.

## Overview

This monorepo contains two packages for working with MongoDB in a type-safe way:

- **typed_mongo**: Runtime package providing MongoDB operators, a collection model base class, type-safe collection wrappers, and aggregation pipeline stage types
- **typed_mongo_gen**: Code generator that introspects Pydantic models and generates comprehensive type definitions for queries, updates, and aggregation pipelines

## Features

- Full type safety — type checker validates field paths, query operators, update values, and aggregation stage parameters
- Automatic code generation — introspects Pydantic models to generate type definitions
- Dual .py/.pyi output — runtime aliases for speed, full type stubs for IDE support
- Glob-based model discovery — accepts glob patterns like `app/models/**/*.py`
- pyproject.toml configuration — define codegen jobs and formatters in your project config
- Aggregation pipeline support — type-safe `$match`, `$sort`, `$set`, `$group`, `$lookup`, and more

## Installation

```bash
# Runtime package only
pip install typed-mongo

# With code generator
pip install typed-mongo-gen
```

## Quick Start

### 1. Define your models

```python
from typed_mongo import MongoCollectionModel

class User(MongoCollectionModel):
    __collection_name__ = "users"

    name: str
    email: str
    age: int | None = None
```

### 2. Generate type definitions

```bash
# From file paths or globs
typed-mongo-gen 'app/models/**/*.py' --output app/_generated_types.py

# Or configure in pyproject.toml and just run:
typed-mongo-gen
```

This generates:
- `app/_generated_types.py` — runtime type aliases
- `app/_generated_types.pyi` — full type definitions for type checkers

### 3. Use the generated types

```python
from app._generated_types import UserCollection, UserQuery

# Type-safe collection wrapper
users = UserCollection(db)

# Type-checked query — typos and wrong types caught by type checker
results = await users.find({"age": {"$gt": 18}, "email": {"$regex": "@example.com"}})

# Type-checked updates
await users.update_one({"name": "Alice"}, {"$set": {"age": 30}})

# Type-safe aggregation pipeline
pipeline: list[UserPipelineStage] = [
    {"$match": {"age": {"$gt": 18}}},
    {"$sort": {"name": 1}},
]
async for user in await users.aggregate(pipeline):
    print(user.name)
```

## Package Documentation

See individual package READMEs for detailed documentation:
- [typed_mongo/README.md](typed_mongo/README.md) — runtime types and operators
- [typed_mongo_gen/README.md](typed_mongo_gen/README.md) — code generator CLI and configuration

## Development

```bash
# Install both packages in development mode
uv sync

# Run tests (run separately per package to avoid import collisions)
cd typed_mongo && uv run pytest
cd typed_mongo_gen && uv run pytest
```

## Architecture

```
typed_mongo/              # Runtime package
├── operators.py          # MongoDB operator TypedDicts + AggregationStep
├── model.py              # MongoCollectionModel base class
└── collection.py         # TypedCollection / TypedCursor wrappers

typed_mongo_gen/          # Generator package
├── introspect.py         # Pydantic model introspection
├── codegen.py            # Type definition generation
└── cli.py                # CLI (cyclopts) + pyproject.toml config
```

## Requirements

- Python 3.12+ (uses PEP 695 type aliases)
- Pydantic 2.0+
- pymongo/motor for MongoDB connection

## License

MIT
