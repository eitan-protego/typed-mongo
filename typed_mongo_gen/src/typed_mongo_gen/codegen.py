"""Code generation for MongoDB field path types.

Generates dual .py/.pyi output files with type definitions for MongoDB queries.
Runtime .py file contains simple aliases, stub .pyi file contains full types.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from typed_mongo_gen.introspect import collect_field_path_types, collect_field_paths

_BUILTINS = frozenset({str, int, float, bool, list, dict, bytes, type(None)})


def _module_alias(module: str) -> str:
    """Convert a dotted module path to a unique Python identifier alias."""
    return "_" + module.replace(".", "_")


def _annotation_to_source(
    annotation: Any, module_aliases: dict[str, str] | None = None
) -> str:
    """Convert a runtime type annotation to a valid Python source string.

    module_aliases maps module path -> alias for types whose module has a
    naming conflict and must be accessed as ``alias.Name``.
    """
    # NoneType
    if annotation is type(None):
        return "None"

    # TypeAliasType -- unwrap
    if isinstance(annotation, typing.TypeAliasType):
        return _annotation_to_source(annotation.__value__, module_aliases)

    origin = get_origin(annotation)

    # Annotated[X, ...] -- unwrap to X
    if origin is typing.Annotated:
        return _annotation_to_source(get_args(annotation)[0], module_aliases)

    # Union / Optional (X | Y)
    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        parts = [_annotation_to_source(a, module_aliases) for a in get_args(annotation)]
        return " | ".join(parts)

    # list[X]
    if origin is list:
        args = get_args(annotation)
        if args:
            return f"list[{_annotation_to_source(args[0], module_aliases)}]"
        return "list"

    # dict[K, V]
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            k = _annotation_to_source(args[0], module_aliases)
            v = _annotation_to_source(args[1], module_aliases)
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
        if annotation in _BUILTINS:
            return annotation.__name__
        module = annotation.__module__
        name = annotation.__name__
        if module_aliases and module in module_aliases:
            return f"{module_aliases[module]}.{name}"
        return name

    return repr(annotation)


def _query_value_type_src(
    annotation: Any, module_aliases: dict[str, str] | None = None
) -> str:
    """Source for the value type inside Op[...] in query TypedDicts.

    For list[T] fields (including nested lists), MongoDB allows matching at any
    nesting level: e.g. list[list[list[Foo]]] allows Foo | list[Foo] |
    list[list[Foo]] | list[list[list[Foo]]]. Other fields use the annotation as-is.
    """
    if isinstance(annotation, typing.TypeAliasType):
        return _query_value_type_src(annotation.__value__, module_aliases)
    origin = get_origin(annotation)
    if origin is typing.Annotated:
        return _query_value_type_src(get_args(annotation)[0], module_aliases)
    if origin is list:
        args = get_args(annotation)
        if args:
            inner_src = _query_value_type_src(args[0], module_aliases)
            full_list_src = _annotation_to_source(annotation, module_aliases)
            return f"{inner_src} | {full_list_src}"
    return _annotation_to_source(annotation, module_aliases)


def _collect_imports(annotation: Any) -> set[tuple[str, str]]:
    """Return set of (module, name) tuples for types that need importing."""
    imports: set[tuple[str, str]] = set()
    _collect_imports_inner(annotation, imports)
    return imports


def _collect_imports_inner(annotation: Any, imports: set[tuple[str, str]]) -> None:
    if annotation is type(None):
        return

    if isinstance(annotation, typing.TypeAliasType):
        _collect_imports_inner(annotation.__value__, imports)
        return

    origin = get_origin(annotation)

    if origin is typing.Annotated:
        _collect_imports_inner(get_args(annotation)[0], imports)
        return

    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports)
        return

    if origin is list:
        args = get_args(annotation)
        if args:
            _collect_imports_inner(args[0], imports)
        return

    if origin is dict:
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports)
        return

    if origin is Literal:
        imports.add(("typing", "Literal"))
        return

    if annotation is Any:
        return

    if isinstance(annotation, type):
        if annotation in _BUILTINS:
            return
        module = annotation.__module__
        name = annotation.__name__
        if module != "builtins":
            imports.add((module, name))


def _build_module_aliases(all_imports: set[tuple[str, str]]) -> dict[str, str]:
    """Detect naming conflicts and return a module -> alias mapping.

    Only modules that export at least one name that conflicts with another
    module are aliased. Non-conflicting modules use direct ``from M import N``
    imports and return an empty alias mapping.
    """
    # Only user-land imports can conflict; typing is always direct
    user_imports = {(m, n) for m, n in all_imports if m != "typing"}

    name_to_modules: dict[str, list[str]] = {}
    for module, name in user_imports:
        name_to_modules.setdefault(name, []).append(module)

    conflicting_modules = {
        m for modules in name_to_modules.values() if len(modules) > 1 for m in modules
    }
    return {m: _module_alias(m) for m in conflicting_modules}


def _write_headers(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    all_imports: set[tuple[str, str]],
    model_imports: dict[str, set[str]],
    module_aliases: dict[str, str],
) -> None:
    """Write headers to both runtime .py and stub .pyi files."""
    header = '''"""Auto-generated MongoDB field path types.

Do not edit manually. Regenerate with:
    typed-mongo-gen <sources> --output <output>
"""

'''

    # Runtime: minimal header — TypedCollection + direct model class imports
    runtime_f.write(header)
    runtime_f.write("from typing import Any\n")
    runtime_f.write("from pymongo.asynchronous.database import AsyncDatabase\n")
    runtime_f.write("from typed_mongo import TypedCollection\n")
    for module in sorted(model_imports):
        names = ", ".join(sorted(model_imports[module]))
        runtime_f.write(f"from {module} import {names}\n")
    runtime_f.write("\n")

    # Stub: full header
    stub_f.write(header)
    stub_f.write("# ruff: noqa: E501\n\n")

    # typing imports (always direct)
    typing_names = {n for m, n in all_imports if m == "typing"}
    typing_names |= {"Literal", "TypedDict", "Any"}
    stub_f.write(f"from typing import {', '.join(sorted(typing_names))}\n")

    # Direct from-imports for non-conflicting user modules
    direct_by_module: dict[str, set[str]] = {}
    for module, name in all_imports:
        if module == "typing":
            continue
        if module not in module_aliases:
            direct_by_module.setdefault(module, set()).add(name)
    for module in sorted(direct_by_module):
        names = sorted(direct_by_module[module])
        stub_f.write(f"from {module} import {', '.join(names)}\n")

    # Aliased imports for conflicting modules
    for module in sorted(module_aliases):
        alias = module_aliases[module]
        stub_f.write(f"import {module} as {alias}\n")

    stub_f.write("from pymongo.asynchronous.database import AsyncDatabase\n")
    stub_f.write("from typed_mongo import TypedCollection\n")
    stub_f.write("from typed_mongo.operators import Op\n")
    stub_f.write("\n")


def _write_model(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    model_name: str,
    model: type[BaseModel],
    path_types: dict[str, Any],
    module_aliases: dict[str, str],
) -> None:
    """Write a model's types and Collection class to both .py and .pyi files."""
    # Runtime: simple aliases + Collection class
    runtime_f.write(f"# {model_name}\n")
    runtime_f.write(f"type {model_name}Path = str\n")
    runtime_f.write(f"{model_name}Query = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Fields = dict[str, Any]\n\n")
    runtime_f.write(f"class {model_name}Collection(TypedCollection):\n")
    runtime_f.write(
        "    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:\n"
    )
    runtime_f.write(
        f"        super().__init__({model_name}, {model_name}.get_collection(db))\n\n\n"
    )

    # Stub: Path Literal
    paths = collect_field_paths(model)
    stub_f.write(f"type {model_name}Path = Literal[\n")
    for path in paths:
        stub_f.write(f'    "{path}",\n')
    stub_f.write("]\n\n")

    # Query TypedDict (with Op[T]; list[T] fields use Op[T | list[T]])
    stub_f.write(f'{model_name}Query = TypedDict("{model_name}Query", {{\n')
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path], module_aliases)
        if type_src == "dict[str, Any]":
            stub_f.write(f'    "{path}": {type_src},\n')
        else:
            query_val_src = _query_value_type_src(path_types[path], module_aliases)
            stub_f.write(f'    "{path}": Op[{query_val_src}],\n')
    stub_f.write('    "$expr": dict[str, Any],\n')
    stub_f.write("}, total=False)\n\n")

    # Fields TypedDict (exact types)
    stub_f.write(f'{model_name}Fields = TypedDict("{model_name}Fields", {{\n')
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path], module_aliases)
        stub_f.write(f'    "{path}": {type_src},\n')
    stub_f.write("}, total=False)\n\n")

    # Collection class — model ref may need aliasing if its module conflicts
    model_ref = _annotation_to_source(model, module_aliases)
    stub_f.write(
        f"class {model_name}Collection("
        + f"TypedCollection[{model_ref}, {model_name}Path, {model_name}Query, {model_name}Fields]"
        + "):\n"
    )
    stub_f.write(
        "    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None: ...\n\n\n"
    )


def write_field_paths(
    runtime_path: Path,
    stub_path: Path,
    models: Mapping[str, type[BaseModel]],
) -> None:
    """Write both runtime .py and stub .pyi files for field path types.

    Args:
        runtime_path: Path to write the runtime .py file
        stub_path: Path to write the stub .pyi file
        models: Dictionary mapping model names to BaseModel classes
    """
    all_imports: set[tuple[str, str]] = set()
    model_path_types: dict[str, dict[str, Any]] = {}
    model_imports: dict[str, set[str]] = {}  # for runtime .py direct imports

    for name, model in models.items():
        path_types = collect_field_path_types(model)
        model_path_types[name] = path_types
        for annotation in path_types.values():
            all_imports |= _collect_imports(annotation)
        # Add the model class itself (needed for Collection class definitions)
        if model.__module__ != "builtins":
            all_imports.add((model.__module__, model.__name__))
            model_imports.setdefault(model.__module__, set()).add(model.__name__)

    module_aliases = _build_module_aliases(all_imports)

    with runtime_path.open("w") as runtime_f, stub_path.open("w") as stub_f:
        _write_headers(runtime_f, stub_f, all_imports, model_imports, module_aliases)

        for name, model in models.items():
            _write_model(
                runtime_f, stub_f, name, model, model_path_types[name], module_aliases
            )
