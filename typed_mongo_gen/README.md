# typed-mongo-gen

Code generator for [typed_mongo](../typed_mongo/README.md). Introspects Pydantic models and emits type-safe `.py`/`.pyi` definitions.

## Installation

```bash
pip install typed-mongo-gen
```

## CLI

```bash
# From file paths or glob patterns (output file auto-excluded from globs)
typed-mongo-gen 'app/models/**/*.py' --output app/_generated_types.py

# With formatters
typed-mongo-gen models.py --output types.py --formatter 'ruff format' --formatter 'ruff check --fix'

# From pyproject.toml config (no arguments needed)
typed-mongo-gen
```

## pyproject.toml configuration

```toml
[tool.typed-mongo-gen.defaults]
formatter = ["ruff format"]

[[tool.typed-mongo-gen.jobs]]
sources = ["app/models/**/*.py"]
output = "app/_generated_types.py"

[[tool.typed-mongo-gen.jobs]]
sources = ["other/models.py"]
output = "other/_types.py"
formatter = ["ruff format", "ruff check --fix"]  # overrides default
```

Each job inherits from `defaults` — any field not set on a job falls back to the default.

## How it works

1. Expands source glob patterns to `.py` files (auto-excluding the output file)
2. Executes each file with `runpy.run_path()` and scans globals for `MongoCollectionModel` subclasses
3. Emits a runtime `.py` (simple aliases) and a `.pyi` stub (full type definitions)

## Generated types per model

| Type | Description |
|------|-------------|
| `{Name}Path` | `Literal` of all valid dot-delimited field paths |
| `{Name}RefPath` | `Literal` of `$`-prefixed paths for aggregation expressions |
| `{Name}OptionalPath` | `Literal` of paths safe to `$unset` (leaf field has a default) |
| `{Name}Dict` | `TypedDict` matching `model_dump()` shape |
| `{Name}Query` | `TypedDict` with `Op[T]` per field + `$and`/`$or`/`$nor`/`$not`/`$expr` |
| `{Name}Fields` | `TypedDict` of all paths with exact value types |
| `{Name}NumericFields` | Numeric field paths mapped to `int \| float` |
| `{Name}UnsetFields` | Optional paths mapped to `Literal[""]` |
| `{Name}Update` | `TypedDict` with `$set`, `$unset`, `$inc`, `$push`, `$pull`, etc. |
| `{Name}PipelineStage` | Union of safe aggregation stages |
| `{Name}UnsafeStage` | Union of shape-changing stages |
| `{Name}Collection` | Concrete `TypedCollection` subclass |
| `{name}_aggregation_step()` | Type-checks an unsafe stage, returns `AggregationStep` |
| `typed_dump()` | Overloaded function: model instance to its `Dict` type |
