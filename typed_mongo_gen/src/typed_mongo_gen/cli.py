"""Command-line interface for typed-mongo-gen."""

import sys
import importlib
import importlib.util
from pathlib import Path

import cyclopts
from typed_mongo import get_registry
from typed_mongo_gen.codegen import write_field_paths


app = cyclopts.App(help="Generate MongoDB field path types from Pydantic models")


def _import_sources(sources: list[str]) -> None:
    """Import modules or files to populate the model registry.

    Args:
        sources: List of module names or file paths to import
    """
    for source in sources:
        source_path = Path(source)

        if source_path.exists() and source_path.is_file():
            # File path - use importlib.util to import
            spec = importlib.util.spec_from_file_location(
                f"__typed_mongo_gen_import_{source_path.stem}__", source_path
            )
            if spec is None or spec.loader is None:
                print(f"ERROR: Cannot load file: {source}", file=sys.stderr)
                sys.exit(1)

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        else:
            # Module path - use standard import
            try:
                importlib.import_module(source)
            except ModuleNotFoundError as e:
                print(f"ERROR: Cannot import module '{source}': {e}", file=sys.stderr)
                sys.exit(1)


@app.default
def generate(
    sources: list[str],
    output: Path = Path("_generated_types.py"),
) -> None:
    """Generate MongoDB field path types from Pydantic models.

    Args:
        sources: Modules or file paths containing MongoCollectionModel subclasses.
                 Auto-detects whether each source is a file path or module name.
        output: Output path for generated runtime .py file.
                A stub .pyi file will be written alongside it.

    Example:
        typed-mongo-gen my_app.models --output generated_types.py
        typed-mongo-gen models/users.py models/products.py --output types.py
    """
    # Import all sources to populate registry
    _import_sources(sources)

    # Get registered models
    registry = get_registry()
    if not registry:
        print(
            f"ERROR: No MongoCollectionModel subclasses found in sources: {sources}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Generate types
    runtime_path = output
    stub_path = output.with_suffix(".pyi")
    write_field_paths(runtime_path, stub_path, registry)

    print(f"Generated {len(registry)} model types:")
    for model_name in sorted(registry.keys()):
        print(f"  - {model_name}")
    print("\nOutput written to:")
    print(f"  {runtime_path.resolve()}")
    print(f"  {stub_path.resolve()}")


if __name__ == "__main__":
    app()
