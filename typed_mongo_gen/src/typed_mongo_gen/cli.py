"""Command-line interface for typed-mongo-gen."""

import importlib
import importlib.util
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import cyclopts

from typed_mongo import clear_registry, get_registry
from typed_mongo_gen.codegen import write_field_paths

app = cyclopts.App(help="Generate MongoDB field path types from Pydantic models")


def _resolve_module_name(source_path: Path) -> str:
    """Resolve the dotted Python module name for a file path via sys.path.

    Compares the absolute file path against each sys.path entry and returns
    the dotted module name if the file is importable from that entry.
    Falls back to a synthetic name if no match is found.
    """
    abs_path = source_path.resolve()
    for entry in sys.path:
        if not entry:
            continue
        entry_path = Path(entry).resolve()
        try:
            rel = abs_path.relative_to(entry_path)
        except ValueError:
            continue
        # Convert path to dotted name, stripping .py
        parts = list(rel.parts)
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)
    # Fallback: synthetic name (imports will be unresolvable, but won't crash)
    return f"__typed_mongo_gen_import_{source_path.stem}__"


def _import_sources(sources: list[str]) -> None:
    """Import modules or files to populate the model registry.

    Args:
        sources: List of module names or file paths to import
    """
    for source in sources:
        source_path = Path(source)

        if source_path.exists() and source_path.is_file():
            # File path - resolve real dotted name so __module__ is correct
            module_name = _resolve_module_name(source_path)
            if module_name in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(module_name, source_path)
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


def _run_after_commands(
    commands: list[str], runtime_path: Path, stub_path: Path
) -> None:
    """Run post-generation commands, appending generated file paths as arguments."""
    for cmd_str in commands:
        argv = shlex.split(cmd_str)
        argv.append(str(runtime_path.resolve()))
        argv.append(str(stub_path.resolve()))
        print(f"  Running: {' '.join(shlex.quote(a) for a in argv)}")
        result = subprocess.run(argv)
        if result.returncode != 0:
            print(
                f"ERROR: Command failed with exit code {result.returncode}: {cmd_str}",
                file=sys.stderr,
            )
            sys.exit(result.returncode)


def _run_single_job(
    sources: list[str],
    output: Path | None,
    run_after: list[str],
) -> None:
    """Run a single codegen job: import sources, generate files, run post-commands."""
    clear_registry()
    _import_sources(sources)

    registry = get_registry()
    if not registry:
        print(
            f"ERROR: No MongoCollectionModel subclasses found in sources: {sources}",
            file=sys.stderr,
        )
        sys.exit(1)

    if output is None:
        output = Path(sources[0]).with_name("_generated_types.py")
    runtime_path = output
    stub_path = output.with_suffix(".pyi")
    write_field_paths(runtime_path, stub_path, registry)

    print(f"Generated {len(registry)} model types:")
    for model_name in sorted(registry.keys()):
        print(f"  - {model_name}")
    print(f"  -> {runtime_path.resolve()}")
    print(f"  -> {stub_path.resolve()}")

    if run_after:
        _run_after_commands(run_after, runtime_path, stub_path)


def _find_pyproject() -> Path | None:
    """Walk up from cwd to find the nearest pyproject.toml."""
    current = Path.cwd().resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _load_pyproject_config() -> dict | None:
    """Load [tool.typed-mongo-gen] from the nearest pyproject.toml."""
    path = _find_pyproject()
    if path is None:
        return None
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("typed-mongo-gen")


def _run_from_config() -> None:
    """Run codegen jobs defined in pyproject.toml [tool.typed-mongo-gen]."""
    config = _load_pyproject_config()
    if config is None:
        print(
            "ERROR: No [tool.typed-mongo-gen] config found in pyproject.toml "
            "and no sources provided on command line.",
            file=sys.stderr,
        )
        sys.exit(1)

    defaults = config.get("defaults", {})
    jobs = config.get("jobs", [])

    if not jobs:
        print(
            "ERROR: No [[tool.typed-mongo-gen.jobs]] entries in pyproject.toml.",
            file=sys.stderr,
        )
        sys.exit(1)

    for i, job in enumerate(jobs):
        sources = job.get("sources", defaults.get("sources"))
        if not sources:
            print(
                f"ERROR: Job {i + 1} has no 'sources' and no default sources.",
                file=sys.stderr,
            )
            sys.exit(1)

        output_str = job.get("output", defaults.get("output"))
        output = Path(output_str) if output_str else None

        run_after = job.get("run_after", defaults.get("run_after", []))

        _run_single_job(sources, output, run_after)


@app.default
def generate(
    sources: list[str] | None = None,
    *,
    output: Path | None = None,
    run_after: list[str] | None = None,
) -> None:
    """Generate MongoDB field path types from Pydantic models.

    Args:
        sources: Modules or file paths containing MongoCollectionModel subclasses.
                 Auto-detects whether each source is a file path or module name.
                 When omitted, runs jobs defined in pyproject.toml.
        output: Output path for generated runtime .py file.
                A stub .pyi file will be written alongside it.
        run_after: Commands to run on the generated files after generation.
                   Each command receives the .py and .pyi paths as arguments.

    Example:
        typed-mongo-gen my_app.models --output generated_types.py
        typed-mongo-gen models/users.py --run-after 'ruff format' --run-after 'ruff check --fix'
        typed-mongo-gen  # runs jobs from pyproject.toml
    """
    if not sources:
        _run_from_config()
        return

    _run_single_job(sources, output, run_after or [])


if __name__ == "__main__":
    app()
