"""Field path introspection for Pydantic models.

Introspects Pydantic models recursively and collects all dot-delimited
MongoDB field paths, handling nested models, lists, unions, and aliases.
"""

from __future__ import annotations

import types
import typing
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

_BUILTINS = frozenset({str, int, float, bool, list, dict, bytes, type(None)})


def collect_field_paths(model: type[BaseModel]) -> list[str]:
    """Return sorted list of all dot-delimited MongoDB field paths for *model*.

    Traverses nested BaseModel subclasses, transparently enters list[Model]
    (MongoDB implicit array navigation), and merges discriminated union
    variants.
    """
    paths: set[str] = set()
    _walk(model, "", paths, frozenset())
    return sorted(paths)


def _resolve_alias(model: type[BaseModel], field_name: str) -> str:
    """Resolve the MongoDB field name for a Pydantic field.

    Checks for explicit validation/serialization alias first,
    then falls back to the model's alias_generator, then the raw name.
    """
    info = model.model_fields[field_name]
    # Explicit alias takes priority (e.g. _id)
    if info.serialization_alias is not None:
        return info.serialization_alias
    if info.validation_alias is not None and isinstance(info.validation_alias, str):
        return info.validation_alias
    # Fall back to alias_generator from model_config
    gen = model.model_config.get("alias_generator")
    if gen is not None:
        return gen(field_name)
    return field_name


def _extract_base_models(annotation: Any) -> list[type[BaseModel]]:
    """Extract concrete BaseModel subclasses from a type annotation.

    Handles: SomeModel, Optional[SomeModel], list[SomeModel],
    Union[A, B], Annotated[Union[A, B], ...], TypeAliasType, etc.
    """
    # TypeAliasType (Python 3.12 `type X = ...`) -- unwrap
    if isinstance(annotation, typing.TypeAliasType):
        return _extract_base_models(annotation.__value__)

    origin = get_origin(annotation)

    # Annotated[X, ...] -- unwrap
    if origin is typing.Annotated:
        return _extract_base_models(get_args(annotation)[0])

    # list[X] -- unwrap element type
    if origin is list:
        args = get_args(annotation)
        if args:
            return _extract_base_models(args[0])
        return []

    # Union / Optional -- collect from each variant
    if origin is types.UnionType or origin is typing.Union:
        result: list[type[BaseModel]] = []
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            result.extend(_extract_base_models(arg))
        return result

    # Concrete BaseModel subclass
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]

    return []


def _walk(
    model: type[BaseModel],
    prefix: str,
    paths: set[str],
    seen: frozenset[type[BaseModel]],
) -> None:
    """Recursively collect dot-delimited field paths.

    *seen* tracks the ancestor chain (models on the current recursion stack)
    to break cycles in self-referential models while still allowing the same
    model to appear at independent positions in the tree.
    """
    for field_name in model.model_fields:
        alias = _resolve_alias(model, field_name)
        full_path = f"{prefix}{alias}" if not prefix else f"{prefix}.{alias}"

        paths.add(full_path)

        annotation = model.model_fields[field_name].annotation
        nested_models = _extract_base_models(annotation)

        for nested in nested_models:
            if nested not in seen:
                _walk(nested, full_path, paths, seen | {nested})


def collect_field_path_types(model: type[BaseModel]) -> dict[str, Any]:
    """Return dict mapping each dot-delimited field path to its Python type annotation.

    Same traversal as collect_field_paths but records the raw annotation
    so the code generator can emit TypedDict mappings.
    """
    path_types: dict[str, Any] = {}
    _walk_with_types(model, "", path_types, frozenset())
    return path_types


def _walk_with_types(
    model: type[BaseModel],
    prefix: str,
    path_types: dict[str, Any],
    seen: frozenset[type[BaseModel]],
) -> None:
    for field_name in model.model_fields:
        alias = _resolve_alias(model, field_name)
        full_path = f"{prefix}{alias}" if not prefix else f"{prefix}.{alias}"

        annotation = model.model_fields[field_name].annotation
        path_types[full_path] = annotation

        nested_models = _extract_base_models(annotation)
        for nested in nested_models:
            if nested not in seen:
                _walk_with_types(nested, full_path, path_types, seen | {nested})
