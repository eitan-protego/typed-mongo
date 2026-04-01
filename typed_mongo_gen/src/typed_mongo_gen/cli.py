"""Command-line interface for typed-mongo-gen."""

import glob
import runpy
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import cyclopts
from pydantic import BaseModel, model_validator

from typed_mongo import MongoCollectionModel


class JobConfig(BaseModel):
    """Configuration for a single codegen job."""
    sources: list[str] | None = None
    output: Path | None = None
    formatter: list[str] = []


class ToolConfig(BaseModel):
    """Schema for [tool.typed-mongo-gen] in pyproject.toml."""
    defaults: JobConfig = JobConfig()
    jobs: list[JobConfig] = []

    @model_validator(mode="after")
    def _apply_defaults(self) -> "ToolConfig":
        for job in self.jobs:
            if job.sources is None:
                job.sources = self.defaults.sources
            if job.output is None:
                job.output = self.defaults.output
            if not job.formatter:
                job.formatter = self.defaults.formatter
        return self
from typed_mongo_gen.codegen import write_field_paths

app = cyclopts.App(help="Generate MongoDB field path types from Pydantic models")


def _resolve_module_name(source_path: Path) -> str:
    """Resolve the dotted Python module name for a file path via sys.path."""
    abs_path = source_path.resolve()
    for entry in sys.path:
        if not entry:
            continue
        entry_path = Path(entry).resolve()
        try:
            rel = abs_path.relative_to(entry_path)
        except ValueError:
            continue
        parts = list(rel.parts)
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)
    return f"__typed_mongo_gen_{source_path.stem}__"


def _collect_models(
    source_paths: list[Path],
) -> dict[str, type[MongoCollectionModel]]:
    """Run each source file and collect MongoCollectionModel subclasses from its globals."""
    models: dict[str, type[MongoCollectionModel]] = {}
    for path in source_paths:
        run_name = _resolve_module_name(path)
        try:
            ns = runpy.run_path(str(path), run_name=run_name)
        except Exception as e:
            print(f"ERROR: Failed to run {path}: {e}", file=sys.stderr)
            sys.exit(1)
        for obj in ns.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, MongoCollectionModel)
                and obj is not MongoCollectionModel
                and "__collection_name__" in obj.__dict__
            ):
                models[obj.__name__] = obj
    return models


def _expand_sources(
    patterns: list[str], exclude: set[Path]
) -> list[Path]:
    """Expand glob patterns to concrete file paths, excluding specified paths."""
    paths: list[Path] = []
    for pattern in patterns:
        expanded = glob.glob(pattern, recursive=True)
        if not expanded:
            print(f"ERROR: No files matched pattern: {pattern}", file=sys.stderr)
            sys.exit(1)
        for p_str in sorted(expanded):
            p = Path(p_str).resolve()
            if p not in exclude:
                paths.append(p)
    return paths


def _run_formatters(
    commands: list[str], runtime_path: Path, stub_path: Path
) -> None:
    """Run formatter commands on generated files, appending file paths as arguments."""
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
    source_patterns: list[str],
    output: Path | None,
    formatter: list[str],
) -> None:
    """Run a single codegen job: expand sources, collect models, generate, run post-commands."""
    # Determine output paths for exclusion
    if output is None:
        first_pattern = source_patterns[0]
        first_expanded = glob.glob(first_pattern, recursive=True)
        if first_expanded:
            output = Path(first_expanded[0]).with_name("_generated_types.py")
        else:
            output = Path("_generated_types.py")
    runtime_path = output.resolve()
    stub_path = output.with_suffix(".pyi").resolve()
    exclude = {runtime_path, stub_path}

    source_paths = _expand_sources(source_patterns, exclude)
    if not source_paths:
        print(
            f"ERROR: No source files found after exclusions for patterns: {source_patterns}",
            file=sys.stderr,
        )
        sys.exit(1)

    models = _collect_models(source_paths)
    if not models:
        print(
            f"ERROR: No MongoCollectionModel subclasses found in: {[str(p) for p in source_paths]}",
            file=sys.stderr,
        )
        sys.exit(1)

    write_field_paths(runtime_path, stub_path, models)

    print(f"Generated {len(models)} model types:")
    for model_name in sorted(models.keys()):
        print(f"  - {model_name}")
    print(f"  -> {runtime_path}")
    print(f"  -> {stub_path}")

    if formatter:
        _run_formatters(formatter, runtime_path, stub_path)


def _find_pyproject() -> Path | None:
    """Walk up from cwd to find the nearest pyproject.toml."""
    current = Path.cwd().resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _load_config() -> ToolConfig | None:
    """Load and validate [tool.typed-mongo-gen] from the nearest pyproject.toml."""
    path = _find_pyproject()
    if path is None:
        return None
    with open(path, "rb") as f:
        data = tomllib.load(f)
    raw = data.get("tool", {}).get("typed-mongo-gen")
    if raw is None:
        return None
    return ToolConfig.model_validate(raw)


def _run_from_config() -> None:
    """Run codegen jobs defined in pyproject.toml [tool.typed-mongo-gen]."""
    config = _load_config()
    if config is None:
        print(
            "ERROR: No [tool.typed-mongo-gen] config found in pyproject.toml "
            "and no sources provided on command line.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not config.jobs:
        print(
            "ERROR: No [[tool.typed-mongo-gen.jobs]] entries in pyproject.toml.",
            file=sys.stderr,
        )
        sys.exit(1)

    for i, job in enumerate(config.jobs):
        if not job.sources:
            print(
                f"ERROR: Job {i + 1} has no 'sources' and no default sources.",
                file=sys.stderr,
            )
            sys.exit(1)
        _run_single_job(job.sources, job.output, job.formatter)


@app.default
def generate(
    sources: list[str] | None = None,
    *,
    output: Path | None = None,
    formatter: list[str] | None = None,
) -> None:
    """Generate MongoDB field path types from Pydantic models.

    Args:
        sources: File paths or glob patterns for files containing MongoCollectionModel
                 subclasses. Glob patterns like 'app/models/**/*.py' are expanded.
                 The output file is automatically excluded from glob matches.
                 When omitted, runs jobs defined in pyproject.toml.
        output: Output path for generated runtime .py file.
                A stub .pyi file will be written alongside it.
        formatter: Formatter commands to run on generated files.
                   Each command receives the .py and .pyi paths as arguments.

    Example:
        typed-mongo-gen 'app/models/**/*.py' --output app/models/_generated_types.py
        typed-mongo-gen models/users.py --formatter 'ruff format' --formatter 'ruff check --fix'
        typed-mongo-gen  # runs jobs from pyproject.toml
    """
    if not sources:
        _run_from_config()
        return

    _run_single_job(sources, output, formatter or [])


if __name__ == "__main__":
    app()
