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

# Enable search types only for selected MongoDB collections
typed-mongo-gen models.py --output types.py --searchable-collections cases

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
searchable_collections = ["cases"]

[[tool.typed-mongo-gen.jobs]]
sources = ["other/models.py"]
output = "other/_types.py"
formatter = ["ruff format", "ruff check --fix"]  # overrides default
```

Each job inherits from `defaults` — any field not set on a job falls back to the default.

`searchable_collections` selects MongoDB names from `__collection_name__`, so renaming a model class does not change the selection. It defaults to `[]`: unselected collections get no search aliases, search imports, or search members in their pipeline unions. Set it in `defaults` to share a selection; an explicit `[]` on a job disables inherited search generation. Unknown collection names are rejected before rewriting that job's output.

The Python API accepts the same selection:

```python
write_field_paths(runtime_path, stub_path, models, searchable_collections={"cases"})
```

Search typing needs only Pydantic field paths and `__collection_name__` for selection; it does not require `MongoCollectionModel` inheritance. The CLI keeps its existing `MongoCollectionModel` discovery because it also generates collection wrappers that use `get_collection()`.

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
| `{Name}SearchStage` | Atlas `$search` stage with model field paths |
| `{Name}SearchOptions` | Search operators, compound clauses, highlighting, sorting, and pagination |
| `{Name}SearchOperator` | A search clause, including recursive compound and embedded document clauses |
| `{Name}SearchMetaStage` | Atlas `$searchMeta` stage, available in the unsafe pipeline suffix |
| `{Name}SearchMetaOptions` | Metadata operators and options, excluding document sorting and highlighting |
| `{Name}UnsafeStage` | Union of shape-changing stages |
| `{Name}Collection` | Concrete `TypedCollection` subclass |
| `{name}_aggregation_step()` | Type-checks an unsafe stage, returns `AggregationStep` |
| `typed_dump()` | Overloaded function: model instance to its `Dict` type |

Search payload schemas live in `typed_mongo.search`. Generated search aliases bind the model's existing `Path` type and recursive clauses; they do not repeat field lists or option schemas for every model. Plain dictionaries and existing typed sort mappings work directly.

`{Name}Search*` types are emitted only for selected collections.
