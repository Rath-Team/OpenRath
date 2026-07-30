"""Small immutable JSON helpers shared by public v2 contracts."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeAlias

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]


def freeze_json(value: object, *, field: str = "value") -> JSONValue:
    """Return an immutable, detached representation of a JSON-compatible value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field} mapping keys must be strings")
            frozen[key] = freeze_json(item, field=f"{field}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            freeze_json(item, field=f"{field}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{field} must be JSON-compatible, got {type(value).__name__}")


def freeze_mapping(
    value: Mapping[str, object] | None,
    *,
    field: str,
) -> Mapping[str, JSONValue]:
    """Freeze a JSON object and return an immutable mapping."""
    frozen = freeze_json(value or {}, field=field)
    assert isinstance(frozen, Mapping)
    return frozen


def thaw_json(value: JSONValue) -> object:
    """Return a mutable JSON-compatible copy suitable for serialization."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value
