"""Pluggable storage for validated feature results."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CacheScope:
    """Who may reuse an entry: everyone (approved curated content) or one user."""

    owner: str

    @classmethod
    def public(cls) -> CacheScope:
        return cls("public")

    @classmethod
    def user(cls, user_id: object) -> CacheScope:
        return cls(f"user:{user_id}")


@dataclass(frozen=True)
class Provenance:
    """How a cached result was generated."""

    deployment_id: str
    model: str
    prompt_version: str
    schema_version: str
    validator_version: str
    created_at: float


@dataclass(frozen=True)
class CacheEntry:
    feature: str
    scope: CacheScope
    value: str
    """The validated result as aliased JSON text, so readers never share state."""
    provenance: Provenance
    expires_at: float


class CacheStore(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def put(self, key: str, entry: CacheEntry) -> None: ...

    def delete(self, key: str) -> None: ...

    def invalidate(self, predicate: Callable[[CacheEntry], bool]) -> int: ...


class InMemoryCacheStore:
    """Thread-safe, capacity-bounded store evicting the least recently used entry."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
            return entry

    def put(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def invalidate(self, predicate: Callable[[CacheEntry], bool]) -> int:
        with self._lock:
            doomed = [key for key, entry in self._entries.items() if predicate(entry)]
            for key in doomed:
                del self._entries[key]
            return len(doomed)
