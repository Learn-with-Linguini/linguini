"""Shared test fixtures: existing suites exercise the demo-auth fallback."""

import os

# Set before app modules are imported so every existing TestClient suite keeps
# using the DEMO_USER_ID fallback instead of requiring bearer tokens.
os.environ.setdefault("AUTH_MODE", "demo")
