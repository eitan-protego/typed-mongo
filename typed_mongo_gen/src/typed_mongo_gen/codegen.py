"""Code generation for MongoDB field path types.

Generates dual .py/.pyi output files with type definitions for MongoDB queries.
Runtime .py file contains simple aliases, stub .pyi file contains full types.
"""

from __future__ import annotations

import re
import types
import typing
from collections.abc import Mapping
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from typed_mongo_gen.introspect import (
    _extract_base_models,
    _resolve_alias,
    collect_field_path_types,
    collect_field_paths,
    collect_optional_paths,
    extract_list_element_type,
    has_default,
    is_numeric_type,
)

_BUILTINS = frozenset({str, int, float, bool, list, dict, bytes, type(None)})


def _all_valid_identifiers(keys: list[str]) -> bool:
    """Check if all keys are valid Python identifiers (usable in class syntax).

    Excludes Python keywords like 'from', 'as', 'class', etc. which are valid
    identifiers but cannot be used as class attribute names.
    """
    import keyword
    return all(k.isidentifier() and not keyword.iskeyword(k) for k in keys)


def _write_typeddict(
    f: typing.TextIO,
    name: str,
    entries: list[tuple[str, str]],
    *,
    total: bool = True,
) -> None:
    """Write a TypedDict using class syntax if possible, else function-call syntax."""
    keys = [k for k, _ in entries]

    # Build extra keyword args string
    extra_kwargs = ""
    if not total:
        extra_kwargs += ", total=False"

    if not entries:
        # Empty TypedDict — always use function-call syntax
        f.write(f'{name} = TypedDict("{name}", {{}}{extra_kwargs})\n\n')
        return

    if _all_valid_identifiers(keys):
        # Class syntax
        f.write(f"class {name}(TypedDict{extra_kwargs}):\n")
        for key, type_str in entries:
            f.write(f"    {key}: {type_str}\n")
        f.write("\n")
    else:
        # Function-call syntax
        f.write(f'{name} = TypedDict("{name}", {{\n')
        for key, type_str in entries:
            f.write(f'    "{key}": {type_str},\n')
        f.write(f"}}{extra_kwargs})\n\n")


def _module_alias(module: str) -> str:
    """Convert a dotted module path to a unique Python identifier alias."""
    return "_" + module.replace(".", "_")


def _literal_repr(value: Any) -> str:
    """Format a value for use inside Literal[...], using double quotes for strings."""
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


def _annotation_to_source(
    annotation: Any,
    module_aliases: dict[str, str] | None = None,
    model_dict_names: dict[type, str] | None = None,
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
        return _annotation_to_source(annotation.__value__, module_aliases, model_dict_names)

    origin = get_origin(annotation)

    # Annotated[X, ...] -- unwrap to X
    if origin is typing.Annotated:
        return _annotation_to_source(get_args(annotation)[0], module_aliases, model_dict_names)

    # Union / Optional (X | Y)
    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        parts = [_annotation_to_source(a, module_aliases, model_dict_names) for a in get_args(annotation)]
        return " | ".join(parts)

    # list[X]
    if origin is list:
        args = get_args(annotation)
        if args:
            return f"list[{_annotation_to_source(args[0], module_aliases, model_dict_names)}]"
        return "list"

    # dict[K, V]
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) == 2:
            k = _annotation_to_source(args[0], module_aliases, model_dict_names)
            v = _annotation_to_source(args[1], module_aliases, model_dict_names)
            return f"dict[{k}, {v}]"
        return "dict"

    # Literal[...]
    if origin is Literal:
        inner = ", ".join(_literal_repr(a) for a in get_args(annotation))
        return f"Literal[{inner}]"

    # typing.Any
    if annotation is Any:
        return "Any"

    # Concrete class (BaseModel subclass, Enum subclass, str, int, etc.)
    if isinstance(annotation, type):
        if annotation in _BUILTINS:
            return annotation.__name__
        # BaseModel subclass with a generated Dict representation
        if model_dict_names and annotation in model_dict_names:
            return model_dict_names[annotation]
        module = annotation.__module__
        name = annotation.__name__
        if module_aliases and module in module_aliases:
            return f"{module_aliases[module]}.{name}"
        return name

    return repr(annotation)


def _query_value_type_src(
    annotation: Any,
    module_aliases: dict[str, str] | None = None,
    model_dict_names: dict[type, str] | None = None,
) -> str:
    """Source for the value type inside Op[...] in query TypedDicts.

    For list[T] fields (including nested lists), MongoDB allows matching at any
    nesting level: e.g. list[list[list[Foo]]] allows Foo | list[Foo] |
    list[list[Foo]] | list[list[list[Foo]]]. For unions (e.g. list[Foo] | None,
    list[Foo] | str), each member is expanded the same way. Other fields use
    the annotation as-is.
    """
    if isinstance(annotation, typing.TypeAliasType):
        return _query_value_type_src(annotation.__value__, module_aliases, model_dict_names)
    origin = get_origin(annotation)
    if origin is typing.Annotated:
        return _query_value_type_src(get_args(annotation)[0], module_aliases, model_dict_names)
    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        parts = [_query_value_type_src(a, module_aliases, model_dict_names) for a in get_args(annotation)]
        return " | ".join(parts)
    if origin is list:
        args = get_args(annotation)
        if args:
            inner_src = _query_value_type_src(args[0], module_aliases, model_dict_names)
            full_list_src = _annotation_to_source(annotation, module_aliases, model_dict_names)
            return f"{inner_src} | {full_list_src}"
    return _annotation_to_source(annotation, module_aliases, model_dict_names)


def _collect_imports(
    annotation: Any, model_dict_names: dict[type, str] | None = None
) -> set[tuple[str, str]]:
    """Return set of (module, name) tuples for types that need importing."""
    imports: set[tuple[str, str]] = set()
    _collect_imports_inner(annotation, imports, model_dict_names)
    return imports


def _collect_imports_inner(
    annotation: Any,
    imports: set[tuple[str, str]],
    model_dict_names: dict[type, str] | None = None,
) -> None:
    if annotation is type(None):
        return

    if isinstance(annotation, typing.TypeAliasType):
        _collect_imports_inner(annotation.__value__, imports, model_dict_names)
        return

    origin = get_origin(annotation)

    if origin is typing.Annotated:
        _collect_imports_inner(get_args(annotation)[0], imports, model_dict_names)
        return

    if origin is types.UnionType or origin is typing.Union:  # pyright: ignore[reportDeprecated]
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports, model_dict_names)
        return

    if origin is list:
        args = get_args(annotation)
        if args:
            _collect_imports_inner(args[0], imports, model_dict_names)
        return

    if origin is dict:
        for arg in get_args(annotation):
            _collect_imports_inner(arg, imports, model_dict_names)
        return

    if origin is Literal:
        imports.add(("typing", "Literal"))
        return

    if annotation is Any:
        return

    if isinstance(annotation, type):
        if annotation in _BUILTINS:
            return
        # Skip BaseModel types that have generated Dict representations
        if model_dict_names and annotation in model_dict_names:
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
    runtime_f.write("from pydantic import BaseModel\n")
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
    typing_names |= {"Literal", "Any", "overload"}
    typing_names |= {"NotRequired", "Required", "TypedDict"}
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
    stub_f.write("from collections.abc import Mapping\n")
    stub_f.write("from typed_mongo.operators import AggExprOp, AggregationStep, Op\n")
    stub_f.write("\n")


def _write_nested_dict(
    stub_f: typing.TextIO,
    model: type[BaseModel],
    dict_name: str,
    module_aliases: dict[str, str],
    model_dict_names: dict[type, str],
) -> None:
    """Write a standalone Dict TypedDict for a nested (non-top-level) model."""
    entries = []
    for field_name in model.model_fields:
        alias = _resolve_alias(model, field_name)
        annotation = model.model_fields[field_name].annotation
        type_str = _annotation_to_source(annotation, module_aliases, model_dict_names)
        entries.append((alias, type_str))
    _write_typeddict(stub_f, dict_name, entries)



def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name)
    s = re.sub(r'(?<=[A-Z])([A-Z][a-z])', r'_\1', s)
    return s.lower()


def _write_model(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    model_name: str,
    model: type[BaseModel],
    path_types: dict[str, Any],
    module_aliases: dict[str, str],
    model_dict_names: dict[type, str],
) -> None:
    """Write a model's types and Collection class to both .py and .pyi files."""
    func_name = _to_snake_case(model_name)

    # Runtime: simple aliases + Collection class
    runtime_f.write(f"# {model_name}\n")
    runtime_f.write(f"type {model_name}Path = str\n")
    runtime_f.write(f"{model_name}Dict = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Query = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Fields = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}NumericFields = dict[str, int | float]\n")
    runtime_f.write(f"type {model_name}ArrayPath = str\n")
    runtime_f.write(f"type {model_name}ArrayElementFields = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}ArrayPushFields = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}ArrayPopFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnsetFields = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}RefPath = str\n")
    runtime_f.write(f"type {model_name}PipelineSetFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}Update = dict[str, Any]\n")
    runtime_f.write(f"{model_name}PipelineSet = dict[str, Any]\n")
    runtime_f.write(f"{model_name}PipelineUnset = dict[str, Any]\n")
    # Aggregation stage aliases
    runtime_f.write(f"type {model_name}OptionalPath = str\n")
    runtime_f.write(f"{model_name}MatchStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SortStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LimitStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SkipStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}SetStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}AddFieldsStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}AggUnsetStage = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}PipelineStage = dict[str, Any]\n")
    # Unsafe stage aliases
    runtime_f.write(f"{model_name}GroupStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}GroupFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnwindStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}UnwindOptions = dict[str, Any]\n")
    runtime_f.write(f"{model_name}ProjectStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketAutoStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}BucketAutoFields = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LookupStage = dict[str, Any]\n")
    runtime_f.write(f"{model_name}LookupFields = dict[str, Any]\n")
    runtime_f.write(f"type {model_name}UnsafeStage = dict[str, Any]\n\n")
    runtime_f.write(f"\ndef {func_name}_aggregation_step(step: dict[str, Any]) -> dict[str, Any]:\n")
    runtime_f.write("    return step\n\n\n")
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

    # Dict TypedDict (top-level fields only, total=True — matches model_dump() output)
    model_entries = [
        (path, _annotation_to_source(path_types[path], module_aliases, model_dict_names))
        for path in sorted(path_types)
        if "." not in path
    ]
    _write_typeddict(stub_f, f"{model_name}Dict", model_entries)

    # Query TypedDict (with Op[T]; list[T] fields use Op[T | list[T]])
    query_entries: list[tuple[str, str]] = []
    for path in sorted(path_types):
        type_src = _annotation_to_source(path_types[path], module_aliases, model_dict_names)
        if type_src == "dict[str, Any]":
            query_entries.append((path, type_src))
        else:
            query_val_src = _query_value_type_src(path_types[path], module_aliases, model_dict_names)
            query_entries.append((path, f"Op[{query_val_src}]"))
    query_entries.append(("$expr", "dict[str, Any]"))
    query_entries.append(("$and", f'list["{model_name}Query"]'))
    query_entries.append(("$or", f'list["{model_name}Query"]'))
    query_entries.append(("$nor", f'list["{model_name}Query"]'))
    query_entries.append(("$not", f'"{model_name}Query"'))
    _write_typeddict(stub_f, f"{model_name}Query", query_entries, total=False)

    # Fields TypedDict (exact types)
    fields_entries = [
        (path, _annotation_to_source(path_types[path], module_aliases, model_dict_names))
        for path in sorted(path_types)
    ]
    _write_typeddict(stub_f, f"{model_name}Fields", fields_entries, total=False)

    # NumericFields: dict keyed by numeric field paths
    numeric_path_list = sorted(p for p, t in path_types.items() if is_numeric_type(t))
    has_numeric = bool(numeric_path_list)
    if has_numeric:
        numeric_keys = ", ".join(f'"{p}"' for p in numeric_path_list)
        stub_f.write(f"type {model_name}NumericFields = dict[Literal[{numeric_keys}], int | float]\n\n")

    # ArrayPath: Literal of all list-typed field paths
    array_path_list = sorted(p for p, t in path_types.items() if extract_list_element_type(t) is not None)
    has_arrays = bool(array_path_list)
    if has_arrays:
        stub_f.write(f"type {model_name}ArrayPath = Literal[\n")
        for p in array_path_list:
            stub_f.write(f'    "{p}",\n')
        stub_f.write("]\n\n")

        # ArrayElementFields, ArrayPushFields, ArrayPopFields: dict keyed by ArrayPath
        stub_f.write(f"type {model_name}ArrayElementFields = dict[{model_name}ArrayPath, Any]\n")
        stub_f.write(f"type {model_name}ArrayPushFields = dict[{model_name}ArrayPath, Any]\n")
        stub_f.write(f"type {model_name}ArrayPopFields = dict[{model_name}ArrayPath, Literal[1, -1]]\n\n")

    # OptionalPath: all paths where the leaf field has a default (can be safely $unset)
    optional_paths = collect_optional_paths(model)
    if optional_paths:
        stub_f.write(f"type {model_name}OptionalPath = Literal[\n")
        for path in sorted(optional_paths):
            stub_f.write(f'    "{path}",\n')
        stub_f.write("]\n\n")
    else:
        stub_f.write(f"type {model_name}OptionalPath = str  # no optional fields\n\n")

    # UnsetFields: only fields with defaults can be unset
    stub_f.write(f'type {model_name}UnsetFields = dict[{model_name}OptionalPath, Literal[""]]\n\n')

    # RefPath: $-prefixed field paths for pipeline expressions (all fields)
    stub_f.write(f"type {model_name}RefPath = Literal[\n")
    for path in paths:
        stub_f.write(f'    "${path}",\n')
    stub_f.write("]\n\n")

    # PipelineSetFields: dict keyed by Path, values are Any (field value, RefPath, or aggregation expr)
    stub_f.write(f"type {model_name}PipelineSetFields = dict[{model_name}Path, Any]\n\n")

    # Update TypedDict (unified update document)
    update_entries: list[tuple[str, str]] = [
        ("$set", f"{model_name}Fields"),
        ("$setOnInsert", f"{model_name}Fields"),
        ("$unset", f"{model_name}UnsetFields"),
    ]
    if has_numeric:
        update_entries.append(("$inc", f"{model_name}NumericFields"))
        update_entries.append(("$mul", f"{model_name}NumericFields"))
    update_entries.append(("$min", f"{model_name}Fields"))
    update_entries.append(("$max", f"{model_name}Fields"))
    if has_arrays:
        update_entries.append(("$push", f"{model_name}ArrayPushFields"))
        update_entries.append(("$pull", f"{model_name}ArrayElementFields"))
        update_entries.append(("$addToSet", f"{model_name}ArrayPushFields"))
        update_entries.append(("$pop", f"{model_name}ArrayPopFields"))
    _write_typeddict(stub_f, f"{model_name}Update", update_entries, total=False)

    # --- Safe aggregation stage TypedDicts ---

    _write_typeddict(stub_f, f"{model_name}MatchStage", [("$match", f"{model_name}Query")])
    _write_typeddict(stub_f, f"{model_name}SortStage", [("$sort", f"dict[{model_name}Path, Literal[1, -1]]")])
    _write_typeddict(stub_f, f"{model_name}LimitStage", [("$limit", "int")])
    _write_typeddict(stub_f, f"{model_name}SkipStage", [("$skip", "int")])
    _write_typeddict(stub_f, f"{model_name}SetStage", [("$set", f"{model_name}PipelineSetFields")])
    _write_typeddict(stub_f, f"{model_name}AddFieldsStage", [("$addFields", "dict[str, Any]")])
    if optional_paths:
        _write_typeddict(stub_f, f"{model_name}AggUnsetStage", [("$unset", f"{model_name}OptionalPath | list[{model_name}OptionalPath]")])

    # PipelineStage union (safe stages only)
    safe_stages = [
        f"{model_name}MatchStage",
        f"{model_name}SortStage",
        f"{model_name}LimitStage",
        f"{model_name}SkipStage",
        f"{model_name}SetStage",
        f"{model_name}AddFieldsStage",
    ]
    if optional_paths:
        safe_stages.append(f"{model_name}AggUnsetStage")
    stub_f.write(f"type {model_name}PipelineStage = (\n")
    for i, stage in enumerate(safe_stages):
        prefix = "    " if i == 0 else "    | "
        stub_f.write(f"{prefix}{stage}\n")
    stub_f.write(")\n\n")

    # --- Model-specific unsafe stage helpers ---

    # $group — _id checked against RefPath
    _write_typeddict(stub_f, f"{model_name}GroupFields", [
        ("_id", f"{model_name}RefPath | list[{model_name}RefPath] | dict[str, {model_name}RefPath] | None"),
    ])
    _write_typeddict(stub_f, f"{model_name}GroupStage", [
        ("$group", f"{model_name}GroupFields"),
    ])

    # $unwind — path checked against RefPath
    _write_typeddict(stub_f, f"{model_name}UnwindOptions", [
        ("path", f"Required[{model_name}RefPath]"),
        ("preserveNullAndEmptyArrays", "bool"),
        ("includeArrayIndex", "str"),
    ], total=False)
    _write_typeddict(stub_f, f"{model_name}UnwindStage", [
        ("$unwind", f"{model_name}RefPath | {model_name}UnwindOptions"),
    ])

    # $project — field names checked against Path
    _write_typeddict(stub_f, f"{model_name}ProjectStage", [
        ("$project", f"dict[{model_name}Path, Literal[0, 1] | dict[str, Any]]"),
    ])

    # $bucket — groupBy checked against RefPath
    _write_typeddict(stub_f, f"{model_name}BucketFields", [
        ("groupBy", f"{model_name}RefPath"),
        ("boundaries", "list[Any]"),
        ("default", "Any"),
        ("output", "NotRequired[dict[str, Any]]"),
    ])
    _write_typeddict(stub_f, f"{model_name}BucketStage", [
        ("$bucket", f"{model_name}BucketFields"),
    ])

    # $bucketAuto — groupBy checked against RefPath
    _write_typeddict(stub_f, f"{model_name}BucketAutoFields", [
        ("groupBy", f"{model_name}RefPath"),
        ("buckets", "int"),
    ])
    _write_typeddict(stub_f, f"{model_name}BucketAutoStage", [
        ("$bucketAuto", f"{model_name}BucketAutoFields"),
    ])

    # $lookup — localField checked against Path
    _write_typeddict(stub_f, f"{model_name}LookupFields", [
        ("from", "str"),
        ("localField", f"{model_name}Path"),
        ("foreignField", "str"),
        ("as", "str"),
    ])
    _write_typeddict(stub_f, f"{model_name}LookupStage", [
        ("$lookup", f"{model_name}LookupFields"),
    ])

    # UnsafeStage union and aggregation_step function
    unsafe_stages = [
        f"{model_name}GroupStage",
        f"{model_name}UnwindStage",
        f"{model_name}ProjectStage",
        f"{model_name}BucketStage",
        f"{model_name}BucketAutoStage",
        f"{model_name}LookupStage",
    ]
    stub_f.write(f"type {model_name}UnsafeStage = (\n")
    for i, stage in enumerate(unsafe_stages):
        prefix = "    " if i == 0 else "    | "
        stub_f.write(f"{prefix}{stage}\n")
    stub_f.write(")\n\n")

    func_name = _to_snake_case(model_name)
    stub_f.write(f"def {func_name}_aggregation_step(step: {model_name}UnsafeStage) -> AggregationStep: ...\n\n")

    # Collection class — model ref needs original class import (not the Dict)
    model_ref = _annotation_to_source(model, module_aliases)
    stub_f.write(
        f"class {model_name}Collection("
        + f"TypedCollection[{model_ref}, {model_name}Dict, {model_name}Path, {model_name}Query, {model_name}Fields, {model_name}Update, {model_name}PipelineStage]"
        + "):\n"
    )
    stub_f.write(
        "    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None: ...\n\n\n"
    )


def _write_typed_dump(
    runtime_f: typing.TextIO,
    stub_f: typing.TextIO,
    models: Mapping[str, type[BaseModel]],
    model_dict_names: dict[type, str],
    module_aliases: dict[str, str],
) -> None:
    """Write the typed_dump() overloaded function to both files."""
    # Runtime: simple implementation that calls model_dump()
    runtime_f.write("def typed_dump(model: BaseModel) -> dict[str, Any]:\n")
    runtime_f.write("    return model.model_dump()\n")

    # Stub: @overload for each top-level model + each nested model
    for model_cls, dict_name in model_dict_names.items():
        model_ref = _annotation_to_source(model_cls, module_aliases)
        stub_f.write("@overload\n")
        stub_f.write(f"def typed_dump(model: {model_ref}) -> {dict_name}: ...\n")
    stub_f.write("\n")


def _collect_all_nested_models(
    models: Mapping[str, type[BaseModel]],
) -> dict[type[BaseModel], str]:
    """Collect all BaseModel types referenced in field annotations and assign Dict names.

    Returns mapping of BaseModel class -> Dict name (e.g., Address -> AddressDict).
    """
    top_level_classes: dict[type[BaseModel], str] = {}
    for name, model in models.items():
        top_level_classes[model] = f"{name}Dict"

    all_models: dict[type[BaseModel], str] = dict(top_level_classes)

    visited: set[type[BaseModel]] = set()
    to_visit: list[type[BaseModel]] = list(models.values())

    while to_visit:
        model = to_visit.pop()
        if model in visited:
            continue
        visited.add(model)

        for field_name in model.model_fields:
            annotation = model.model_fields[field_name].annotation
            for nested in _extract_base_models(annotation):
                if nested not in all_models:
                    all_models[nested] = f"{nested.__name__}Dict"
                    to_visit.append(nested)

    return all_models


def _topological_order(
    all_models: dict[type[BaseModel], str],
) -> list[type[BaseModel]]:
    """Return models in dependency order (dependencies first) using graphlib."""
    graph: dict[type[BaseModel], set[type[BaseModel]]] = {}
    for model in all_models:
        deps: set[type[BaseModel]] = set()
        for field_name in model.model_fields:
            annotation = model.model_fields[field_name].annotation
            for nested in _extract_base_models(annotation):
                if nested in all_models and nested is not model:
                    deps.add(nested)
        graph[model] = deps

    ts = TopologicalSorter(graph)
    return list(ts.static_order())


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
    # Collect all nested BaseModel types and assign Dict names
    model_dict_names = _collect_all_nested_models(models)
    top_level_classes = set(models.values())

    all_imports: set[tuple[str, str]] = set()
    model_path_types: dict[str, dict[str, Any]] = {}
    model_imports: dict[str, set[str]] = {}  # for runtime .py direct imports

    for name, model in models.items():
        path_types = collect_field_path_types(model)
        model_path_types[name] = path_types
        for annotation in path_types.values():
            all_imports |= _collect_imports(annotation, model_dict_names)
        # Add the model class itself (needed for Collection class and typed_dump)
        if model.__module__ != "builtins":
            all_imports.add((model.__module__, model.__name__))
            model_imports.setdefault(model.__module__, set()).add(model.__name__)

    # Add all introspected model classes (needed for typed_dump overloads)
    for model_cls in model_dict_names:
        if model_cls.__module__ != "builtins":
            all_imports.add((model_cls.__module__, model_cls.__name__))

    module_aliases = _build_module_aliases(all_imports)

    # Determine emission order: nested-only Dicts first, then top-level models
    sorted_models = _topological_order(model_dict_names)

    with runtime_path.open("w") as runtime_f, stub_path.open("w") as stub_f:
        _write_headers(runtime_f, stub_f, all_imports, model_imports, module_aliases)

        # Emit standalone Dict TypedDicts for nested-only models (in dependency order)
        for model_cls in sorted_models:
            if model_cls not in top_level_classes:
                dict_name = model_dict_names[model_cls]
                _write_nested_dict(
                    stub_f, model_cls, dict_name, module_aliases, model_dict_names
                )

        # Emit top-level models in dependency order
        # Build reverse lookup: model class -> model name
        class_to_name = {model: name for name, model in models.items()}
        for model_cls in sorted_models:
            if model_cls in top_level_classes:
                name = class_to_name[model_cls]
                _write_model(
                    runtime_f, stub_f, name, model_cls,
                    model_path_types[name], module_aliases, model_dict_names,
                )

        # Emit typed_dump() function
        _write_typed_dump(
            runtime_f, stub_f, models, model_dict_names, module_aliases,
        )
