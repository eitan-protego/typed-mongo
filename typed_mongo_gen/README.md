# typed-mongo-gen

CLI tool to generate type-safe MongoDB field path definitions from Pydantic models.

## Installation

```bash
pip install typed-mongo-gen
```

## Usage

```bash
typed-mongo-gen my_app.models --output generated_types.py
```

This will:
1. Import the specified module(s) or file(s)
2. Discover all MongoCollectionModel subclasses via registry
3. Generate type definitions in `generated_types.py` and `generated_types.pyi`

## Generated Types

For each model, generates:
- `ModelNamePath`: Literal type of all valid field paths
- `ModelNameQuery`: TypedDict for find/update queries with Op[T] operators
- `ModelNameFields`: TypedDict for field projection specifications
