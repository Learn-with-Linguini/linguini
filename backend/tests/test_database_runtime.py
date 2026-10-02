"""The deployed application requires PostgreSQL, even with stale JSON switches."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.mark.parametrize("legacy_storage", ["json", "postgres"])
def test_missing_database_fails_at_startup(monkeypatch, legacy_storage):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USER_STORAGE", legacy_storage)
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        with TestClient(create_app()):
            pytest.fail("Application must not start without database configuration")
