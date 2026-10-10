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
