# typed_mongo

Type-safe MongoDB operators and collection models.

## Features

- MongoDB operator TypedDicts (Eq, Ne, In, Gt, etc.)
- MongoCollectionModel base class with automatic registry
- TypedCollection and TypedCursor wrappers for type-safe queries

## Installation

```bash
pip install typed-mongo
```

## Usage

```python
from typed_mongo import MongoCollectionModel, Op

class User(MongoCollectionModel):
    __collection_name__ = "users"

    name: str
    age: int
```
