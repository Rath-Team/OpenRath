"""Small fail-closed JSON Schema subset used for Tool runtime validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["SchemaValidationError", "validate_json"]


class SchemaValidationError(ValueError):
    pass


def validate_json(value: object, schema: Mapping[str, object], *, path: str = "$") -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"{path} must be an object")
        required = schema.get("required", ())
        if isinstance(required, Sequence) and not isinstance(required, str):
            for key in required:
                if str(key) not in value:
                    raise SchemaValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, item in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, Mapping):
                    validate_json(item, child_schema, path=f"{path}.{key}")
                elif schema.get("additionalProperties") is False:
                    raise SchemaValidationError(f"{path}.{key} is not allowed")
    elif expected == "array":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise SchemaValidationError(f"{path} must be an array")
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                validate_json(item, items, path=f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path} must be a string")
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            raise SchemaValidationError(f"{path} exceeds maxLength")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be an integer")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be a number")
    elif expected == "boolean" and not isinstance(value, bool):
        raise SchemaValidationError(f"{path} must be a boolean")
    elif expected == "null" and value is not None:
        raise SchemaValidationError(f"{path} must be null")
    elif expected not in (None, "object", "array", "string", "integer", "number", "boolean", "null"):
        raise SchemaValidationError(f"{path} uses unsupported schema type {expected!r}")
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and value not in enum:
        raise SchemaValidationError(f"{path} is not an allowed enum value")
