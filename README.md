# Typed MongoDB

Type-safe MongoDB operations for Python using Pydantic model introspection.

## Overview

This monorepo contains two packages for working with MongoDB in a type-safe way:

- **typed_mongo**: Runtime package providing MongoDB operators, collection model base class with automatic registry, and type-safe collection wrappers
- **typed_mongo_gen**: Code generator that introspects Pydantic models and generates comprehensive type definitions for MongoDB queries and projections

## Features

- 🎯 **Full type safety** - Type checker validates field paths, operators, and value types
- 🔄 **Automatic code generation** - Introspects Pydantic models to generate type definitions
- 📝 **Stub files for IDE support** - Dual .py/.pyi output for runtime compatibility and type checking
- 🪝 **Automatic registry** - Models self-register when defined via `__init_subclass__` hook
- 🎨 **Clean API** - Simple, Pythonic interfaces with minimal boilerplate

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
typed-mongo-gen my_app.models --output my_app/types.py
```

This generates:
- `my_app/types.py` - Runtime type aliases
- `my_app/types.pyi` - Full type definitions for type checkers

### 3. Use the generated types

```python
from my_app.types import UserQuery, UserFields
from typed_mongo.operators import Op

# Type-checked query
query: UserQuery = {
    "age": {"$gt": 18},
    "email": {"$regex": "@example.com"}
}

# Type-checked projection
fields: UserFields = {
    "name": 1,
    "email": 1,
    "_id": 0
}

# Use with MongoDB
users = User.get_collection(db)
results = await users.find(query, projection=fields).to_list()
```

## Package Documentation

See individual package READMEs for detailed documentation:
- [typed_mongo/README.md](typed_mongo/README.md)
- [typed_mongo_gen/README.md](typed_mongo_gen/README.md)

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/typed-mongo.git
cd typed-mongo

# Install both packages in development mode
uv sync

# Run tests
cd typed_mongo && uv run pytest
cd typed_mongo_gen && uv run pytest

# Format and lint
uv run ruff format .
uv run ruff check .
```

## Architecture

```
typed_mongo/              # Runtime package
├── operators.py          # MongoDB operator TypedDicts
├── model.py              # MongoCollectionModel with registry
└── collection.py         # TypedCollection wrappers

typed_mongo_gen/          # Generator package
├── introspect.py         # Pydantic model introspection
├── codegen.py            # Type definition generation
└── cli.py                # CLI using cyclopts
```

## Requirements

- Python 3.12+ (uses PEP 695 type aliases)
- Pydantic 2.0+
- pymongo/motor for MongoDB connection

## License

MIT
