# typed-mongo-gen

CLI tool to generate type-safe MongoDB field path definitions from Pydantic models.

## Installation

```bash
pip install typed-mongo-gen
```

## Usage

### CLI

```bash
# Generate from specific files
typed-mongo-gen app/models/users.py app/models/products.py --output app/_generated_types.py

# Generate from glob patterns (output file auto-excluded)
typed-mongo-gen 'app/models/**/*.py' --output app/models/_generated_types.py

# Run a formatter on generated files
typed-mongo-gen 'app/models/**/*.py' --output app/_types.py --formatter 'ruff format'

# Multiple formatters
typed-mongo-gen models.py --output types.py --formatter 'ruff format' --formatter 'ruff check --fix'

# Run jobs from pyproject.toml (no arguments needed)
typed-mongo-gen
```

### pyproject.toml configuration

Define codegen jobs in your `pyproject.toml` so you can run `typed-mongo-gen` with no arguments:

```toml
[tool.typed-mongo-gen.defaults]
formatter = ["ruff format", "ruff check --fix"]

[[tool.typed-mongo-gen.jobs]]
sources = ["app/models/**/*.py"]
output = "app/_generated_types.py"

[[tool.typed-mongo-gen.jobs]]
sources = ["other/models.py"]
output = "other/_generated_types.py"
```

Each job inherits from `[tool.typed-mongo-gen.defaults]` — any field not set on a job falls back to the default. Jobs can override any default.

## How it works

1. Expands source glob patterns to concrete `.py` file paths (auto-excluding the output file)
2. Executes each source file with `runpy.run_path()` and scans its globals for `MongoCollectionModel` subclasses
3. Generates a runtime `.py` file (simple `dict[str, Any]` aliases) and a `.pyi` stub (full type definitions)

## Generated types

For each model, generates:

| Type | Description |
|------|-------------|
| `{Name}Path` | `Literal` of all valid dot-delimited field paths |
| `{Name}RefPath` | `Literal` of `$`-prefixed field paths for aggregation expressions |
| `{Name}OptionalPath` | `Literal` of paths where the leaf field has a default (safe to `$unset`) |
| `{Name}Dict` | `TypedDict` matching `model_dump()` output |
| `{Name}Query` | `TypedDict` with `Op[T]` operators per field, plus `$and`/`$or`/`$nor`/`$not`/`$expr` |
| `{Name}Fields` | `TypedDict` of all paths with exact value types |
| `{Name}NumericFields` | `dict` of numeric field paths to `int \| float` |
| `{Name}UnsetFields` | `dict` of optional paths to `Literal[""]` |
| `{Name}Update` | `TypedDict` with `$set`, `$unset`, `$inc`, `$push`, `$pull`, etc. |
| `{Name}PipelineSetFields` | `dict` of paths for `$set`/`$addFields` in aggregation |
| `{Name}PipelineStage` | Union of safe aggregation stages (match, sort, limit, skip, set, addFields, unset) |
| `{Name}UnsafeStage` | Union of shape-changing stages (group, unwind, project, lookup, bucket) |
| `{Name}Collection` | Concrete `TypedCollection` subclass with all type parameters filled |
| `{name}_aggregation_step()` | Identity function that type-checks an unsafe stage and returns `AggregationStep` |
| `typed_dump()` | Overloaded function mapping each model to its `Dict` type |
