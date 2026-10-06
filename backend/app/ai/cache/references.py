"""Session-independent aliases for the scene references in a feature payload.

Payloads key objects, attributes and relationships by session-specific IDs.
Aliases are assigned from content, not IDs, so the same scene in another
session canonicalizes to the same payload. Duplicate objects keep separate
aliases and relationships keep pointing at the right ones.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

REFERENCE_FIELDS = frozenset({
    "key",
    "objectKey",
    "subjectObjectKey",
    "referenceObjectKey",
    "answerObjectKey",
    "objectKeys",
    "attributeKeys",
    "relationshipKeys",
})
_TERM_FIELDS = ("objects", "attributes", "relationships")


def _alias_order(alias: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", alias))


def _signature(row: Mapping[str, Any], aliases: Mapping[str, str]) -> str:
    return json.dumps(
        _map({k: v for k, v in row.items() if k != "key"}, aliases),
        sort_keys=True,
        ensure_ascii=False,
    )


def _map(value: Any, aliases: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            field: _map_reference(item, aliases) if field in REFERENCE_FIELDS
            else _map(item, aliases)
            for field, item in value.items()
        }
    if isinstance(value, list):
        return [_map(item, aliases) for item in value]
    return value


def _map_reference(value: Any, aliases: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, list):
        return [aliases.get(item, item) if isinstance(item, str) else item for item in value]
    return value


def _references(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for field, item in value.items():
            if field in REFERENCE_FIELDS:
                items = item if isinstance(item, list) else [item]
                found.update(entry for entry in items if isinstance(entry, str))
            else:
                found |= _references(item)
    elif isinstance(value, list):
        for item in value:
            found |= _references(item)
    return found


class ReferenceMap:
    """Maps one payload's references to aliases (``o1``, ``o1:color``, ``r1``) and back."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        objects = list(payload.get("objects", []))
        attributes = list(payload.get("attributes", []))
        relationships = list(payload.get("relationships", []))
        attributes_by_object: dict[str, list[str]] = {}
        for row in attributes:
            owner = row.get("objectKey") or str(row["key"]).rpartition(":")[0]
            attributes_by_object.setdefault(owner, []).append(
                _signature({**row, "objectKey": None}, {})
            )
        ordered_objects = sorted(
            objects,
            key=lambda row: (
                _signature(row, {}),
                sorted(attributes_by_object.get(row["key"], [])),
            ),
        )
        aliases: dict[str, str] = {}
        for index, row in enumerate(ordered_objects, start=1):
            aliases.setdefault(row["key"], f"o{index}")
        used = set(aliases.values())
        attribute_aliases: dict[str, str] = {}
        for index, row in enumerate(attributes, start=1):
            owner, separator, name = str(row["key"]).rpartition(":")
            alias = f"{aliases[owner]}:{name}" if separator and owner in aliases else ""
            if not alias or alias in used:
                alias = f"a{index}"
            used.add(alias)
            attribute_aliases.setdefault(row["key"], alias)
        aliases.update(attribute_aliases)
        ordered_relationships = sorted(
            relationships, key=lambda row: _signature(row, aliases)
        )
        for index, row in enumerate(ordered_relationships, start=1):
            aliases.setdefault(row["key"], f"r{index}")
        self._aliases = aliases
        self._keys = {alias: key for key, alias in aliases.items()}

    def canonical_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """``payload`` with aliases for references and terms in alias order."""
        canonical = _map(dict(payload), self._aliases)
        for field in _TERM_FIELDS:
            if field in payload:
                rows = sorted(
                    zip(payload[field], canonical[field], strict=True),
                    key=lambda pair: _alias_order(self._aliases.get(pair[0]["key"], "")),
                )
                canonical[field] = [row for _original, row in rows]
        return canonical

    def to_aliases(self, result: Any) -> Any | None:
        """A result with every reference aliased, or ``None`` if one is unknown."""
        if not _references(result) <= self._aliases.keys():
            return None
        return _map(result, self._aliases)

    def remap(self, result: Any, target: ReferenceMap) -> Any:
        """Map known references directly to another payload, preserving unknowns.

        Flights may share results containing references unsuitable for storage.
        Direct mapping avoids mistaking an unknown key such as ``o1`` for an alias.
        The receiver must still revalidate the mapped result.
        """
        keys = {
            key: target._keys[alias]
            for key, alias in self._aliases.items()
            if alias in target._keys
        }
        return _map(result, keys)

    def from_aliases(self, cached: Any) -> Any:
        """A cached result with aliases replaced by this payload's references.

        Unknown aliases are left in place so revalidation rejects them.
        """
        return _map(cached, self._keys)
