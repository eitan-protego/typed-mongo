"""Code generation for MongoDB field path types.

Generates dual .py/.pyi output files with type definitions for MongoDB queries.
Runtime .py file contains simple aliases, stub .pyi file contains full types.
"""

from __future__ import annotations

import types
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from typed_mongo_gen.introspect import collect_field_paths, collect_field_path_types

_BUILTINS = frozenset({str, int, float, bool, list, dict, bytes, type(None)})


def _annotation_to_source(annotation: Any) -> str:
    """Convert a runtime type annotation to a valid Python source string."""
    # NoneType
    if annotation is type(None):
        return "None"

    # TypeAliasType -- unwrap
    if isinstance(annotation, typing.TypeAliasType):
        return _annotation_to_source(annotation.__value__)

    origin = get_origin(annotation)

    # Annotated[X, ...] -- unwrap to X
    if origin is typing.Annotated:
        return _annotation_to_source(get_args(annotation)[0])

    # Union / Optional (X | Y)
    if origin is types.UnionType or origin is typing.Union:
        parts = [_annotation_to_source(a) for a in get_args(annotation)]
        return " | ".join(parts)

    # list[X]
    if origin is list:
        args = get_args(annotation)
        if args:
            return f"list[{_annotation_to_source(args[0])}]"
        return "list"

    # dict[K, V]
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            k = _annotation_to_source(args[0])
            v = _annotation_to_source(args[1])
            return f"dict[{k}, {v}]"
        return "dict"

    # Literal[...]
    if origin is Literal:
        inner = ", ".join(repr(a) for a in get_args(annotation))
        return f"Literal[{inner}]"

    # typing.Any
    if annotation is Any:
        return "Any"

    # Concrete class (BaseModel subclass, Enum subclass, str, int, etc.)
    if isinstance(annotation, type):
        return annotation.__name__

    return repr(annotation)


def _collect_imports(annotation: Any) -> set[tuple[str, str]]:
    """Return set of (module, name) tuples for types that need importing.

    Builtins (str, int, float, bool, list, dict, bytes, NoneType) need no import.
    """
    imports: set[tuple[str, str]] = set()
    _collect_imports_inner(annotation, imports)
    return imports


def _collect_imports_inner(annotation: Any, imports: set[tuple[str, str]]) -> None:
    # NoneType -- no import needed
    if annotation is type(None):
        return

    # TypeAliasType -- unwrap
    if isinstance(annotation, typing.TypeAliasType):
        _collect_imports_inner(annotation.__value__, imports)
        return

    origin = get_origin(annotation)

    # Annotated[X, ...] -- unwrap
    if origin is typing.Annotated:
        _collect_imports_inner(get_args(annotation)[0], imports)
        return

    # Union / Optional
    if origin is types.UnionType or origin is typing.Union:
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports)
        return

    # list[X]
    if origin is list:
        args = get_args(annotation)
        if args:
            _collect_imports_inner(args[0], imports)
        return

    # dict[K, V]
    if origin is dict:
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports)
        return

    # Literal[...] -- needs typing.Literal import
    if origin is Literal:
        imports.add(("typing", "Literal"))
        return

    # typing.Any
    if annotation is Any:
        # Already imported as part of the header
        return

    # Concrete class
    if isinstance(annotation, type):
        if annotation in _BUILTINS:
            return
        module = annotation.__module__
        name = annotation.__name__
        if module != "builtins":
            imports.add((module, name))


def _write_headers(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    all_imports: set[tuple[str, str]],
) -> None:
    """Write headers to both runtime .py and stub .pyi files."""
    header = '''"""Auto-generated MongoDB field path types.

Do not edit manually. Regenerate with:
    typed-mongo-gen <sources> --output <output>
"""

'''

    # Runtime: minimal header
    runtime_f.write(header)
    runtime_f.write("from typing import Any\n\n")

    # Stub: full header with all imports
    stub_f.write(header)
    stub_f.write("# ruff: noqa: E501\n\n")

    # Build import lines for stub
    imports_by_module: dict[str, set[str]] = {}
    for module, type_name in all_imports:
        imports_by_module.setdefault(module, set()).add(type_name)

    # typing imports: always need Literal, TypedDict, Any
    typing_names = imports_by_module.pop("typing", set())
    typing_names |= {"Literal", "TypedDict", "Any"}
    stub_f.write(f"from typing import {', '.join(sorted(typing_names))}\n")

    # Other imports, sorted by module
    for module in sorted(imports_by_module):
        names = sorted(imports_by_module[module])
        stub_f.write(f"from {module} import {', '.join(names)}\n")

    stub_f.write("from typed_mongo.operators import Op\n")
    stub_f.write("\n")


def _write_model(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    model_name: str,
    model: type[BaseModel],
    path_types: dict[str, Any],
) -> None:
    """Write a model's types to both runtime .py and stub .pyi files."""
    # Runtime: simple aliases with comment header
    runtime_f.write(f"# {model_name}\n")
    runtime_f.write(f"type {model_name}Path = str\n")
    runtime_f.write(f"{model_name}Query = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Fields = dict[str, Any]\n\n")

    # Stub: full type definitions
    # Path Literal
    paths = collect_field_paths(model)
    stub_f.write(f"type {model_name}Path = Literal[\n")
    for path in paths:
        stub_f.write(f'    "{path}",\n')
    stub_f.write("]\n\n")

    # Query TypedDict (with Op[T])
    stub_f.write(f'{model_name}Query = TypedDict("{model_name}Query", {{\n')
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path])
        if type_src == "dict[str, Any]":
            stub_f.write(f'    "{path}": {type_src},\n')
        else:
            stub_f.write(f'    "{path}": Op[{type_src}],\n')
    stub_f.write("}, total=False)\n\n")

    # Fields TypedDict (exact types)
    stub_f.write(f'{model_name}Fields = TypedDict("{model_name}Fields", {{\n')
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path])
        stub_f.write(f'    "{path}": {type_src},\n')
    stub_f.write("}, total=False)\n\n")


def write_field_paths(
    runtime_path: Path,
    stub_path: Path,
    models: dict[str, type[BaseModel]],
) -> None:
    """Write both runtime .py and stub .pyi files for field path types.

    Args:
        runtime_path: Path to write the runtime .py file
        stub_path: Path to write the stub .pyi file
        models: Dictionary mapping model names to BaseModel classes
    """
    # First pass: collect all imports needed for type annotations
    all_imports: set[tuple[str, str]] = set()
    model_path_types: dict[str, dict[str, Any]] = {}

    for name, model in models.items():
        path_types = collect_field_path_types(model)
        model_path_types[name] = path_types
        for annotation in path_types.values():
            all_imports |= _collect_imports(annotation)

    # Write both files
    with runtime_path.open("w") as runtime_f, stub_path.open("w") as stub_f:
        _write_headers(runtime_f, stub_f, all_imports)

        for name, model in models.items():
            _write_model(runtime_f, stub_f, name, model, model_path_types[name])
