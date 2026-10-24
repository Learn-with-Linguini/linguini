"""Strict structured-output schemas derived from Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_STRIPPED_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "default",
        "format",
        "title",
        "$defs",
        "$id",
        "$schema",
    }
)


def _strictify(
    node: Any, defs: dict[str, Any], *, property_map: bool = False
) -> Any:
    """Recursively inline $refs and enforce strict-mode constraints in place."""
    if isinstance(node, list):
        return [_strictify(item, defs) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ValueError(f"unsupported schema reference {ref!r}")
        target = defs[ref.removeprefix("#/$defs/")]
        return _strictify(target, defs)

    schema = {
        key: _strictify(value, defs, property_map=key == "properties")
        for key, value in node.items()
        if property_map or key not in _STRIPPED_KEYWORDS
    }
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"])
    return schema


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive a strict structured-output schema from a Pydantic model.

    Inlines ``$defs``/``$ref``, closes every object
    (``additionalProperties: false``), marks all properties required, and strips
    keywords strict mode rejects.
    """
    raw = model.model_json_schema(by_alias=True)
    defs = raw.get("$defs", {})
    return _strictify(raw, defs)


def _is_map(node: Any) -> bool:
    """An object node whose keys are free-form (``dict[str, X]``), not listed properties."""
    return (
        isinstance(node, dict) and node.get("type") == "object" and "properties" not in node
        and isinstance(node.get("additionalProperties"), dict)
    )


def _pairs(node: Any) -> Any:
    """``node`` with every free-form map replaced by a list of ``{key, value}`` pairs."""
    if isinstance(node, list):
        return [_pairs(item) for item in node]
    if not isinstance(node, dict):
        return node
    if _is_map(node):
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": _pairs(node["additionalProperties"]),
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        }
    return {
        key: (
            {name: _pairs(value) for name, value in child.items()}
            if key == "properties" else _pairs(child)
        )
        for key, child in node.items()
    }


def build_pairs_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The strict schema with ``dict[str, X]`` fields sent as ``[{key, value}]`` lists.

    Strict structured output only accepts closed objects, so free-form maps cannot
    be generated directly. ``restore_maps`` turns a reply back into the model's shape.
    """
    return _pairs(build_strict_json_schema(model))


def _matches(node: dict[str, Any], data: Any) -> bool:
    kind = node.get("type")
    if _is_map(node):
        return isinstance(data, list | dict)
    return {
        "null": data is None, "object": isinstance(data, dict),
        "array": isinstance(data, list), "string": isinstance(data, str),
        "boolean": isinstance(data, bool),
        "integer": isinstance(data, int) and not isinstance(data, bool),
        "number": isinstance(data, int | float) and not isinstance(data, bool),
    }.get(kind, True)


def _restore(node: Any, data: Any) -> Any:
    if not isinstance(node, dict) or data is None:
        return data
    if "anyOf" in node:
        branch = next((item for item in node["anyOf"] if _matches(item, data)), None)
        return data if branch is None else _restore(branch, data)
    if _is_map(node):
        if isinstance(data, list):
            return {
                item["key"]: _restore(node["additionalProperties"], item["value"])
                for item in data
                if isinstance(item, dict) and "key" in item and "value" in item
            }
        return data
    if isinstance(data, dict) and "properties" in node:
        properties = node["properties"]
        return {
            key: _restore(properties[key], value) if key in properties else value
            for key, value in data.items()
        }
    if isinstance(data, list) and "items" in node:
        return [_restore(node["items"], item) for item in data]
    return data


def restore_maps(model: type[BaseModel], data: Any) -> Any:
    """Undo ``build_pairs_json_schema``: ``[{key, value}]`` lists become maps again."""
    return _restore(build_strict_json_schema(model), data)
