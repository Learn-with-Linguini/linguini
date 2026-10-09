"""Routed text and vision clients: deployment priority, credential rotation
and a shared per-invocation deadline and call budget."""

from app.ai.routing.invocation import InvocationContext
from app.ai.routing.router import (
    FixedCredential,
    RoutedModelClient,
    RouteTarget,
    as_routed,
    fails_over,
    route_metadata,
    total_tokens,
)

__all__ = [
    "FixedCredential",
    "InvocationContext",
    "RouteTarget",
    "RoutedModelClient",
    "as_routed",
    "fails_over",
    "route_metadata",
    "total_tokens",
]
