"""Structured action values for :class:`rath.env.OpenRathEnv`."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from rath.env.observations import jsonable_value

__all__ = ["ToolAction"]


def _snapshot(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    copied = deepcopy(dict(value))
    jsonable_value(copied, path=name)
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class ToolAction:
    """One immutable, structured flow-tool call supplied by an actor."""

    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        object.__setattr__(self, "arguments", _snapshot(self.arguments, "arguments"))
        object.__setattr__(self, "metadata", _snapshot(self.metadata, "metadata"))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ToolAction":
        if not isinstance(raw, Mapping):
            raise TypeError("ToolAction input must be a mapping")
        if "tool_name" not in raw:
            raise ValueError("ToolAction mapping requires 'tool_name'")
        return cls(
            tool_name=raw["tool_name"],
            arguments=raw.get("arguments", {}),
            metadata=raw.get("metadata", {}),
        )

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": jsonable_value(self.arguments, path="arguments"),
            "metadata": jsonable_value(self.metadata, path="metadata"),
        }
