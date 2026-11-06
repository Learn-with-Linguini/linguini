"""Every Prisma application table stays behind the API's database role."""

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import create_database_engine


def _application_tables() -> tuple[str, ...]:
    schema = (Path(__file__).resolve().parents[1] / "prisma" / "schema.prisma").read_text()
    models = re.findall(r"(?ms)^model\s+(\w+)\s*\{(.*?)^\}", schema)
    assert models, "No Prisma models found; update the schema inventory parser."
    return tuple(
        mapping.group(1) if (mapping := re.search(r'@@map\("([^"\n]+)"\)', body)) else name
        for name, body in models
    )


APPLICATION_TABLES = _application_tables()


@pytest.fixture
def database(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated disposable test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    try:
        yield engine
    finally:
        engine.dispose()


def test_every_application_table_has_row_security(database):
    with database.connect() as connection:
        rows = connection.execute(text("""
            SELECT c.relname, c.relrowsecurity
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        """)).all()
    actual = dict(rows)
    assert set(APPLICATION_TABLES) <= actual.keys(), "Apply all Prisma migrations before testing."
    assert [name for name in APPLICATION_TABLES if not actual[name]] == []


def test_application_tables_have_no_public_or_browser_grants(database):
    with database.connect() as connection:
        grants = connection.execute(text("""
            SELECT c.relname, COALESCE(r.rolname, 'PUBLIC'), acl.privilege_type
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(c.relacl, acldefault('r', c.relowner))
            ) AS acl
            LEFT JOIN pg_roles AS r ON r.oid = acl.grantee
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                AND (acl.grantee = 0 OR r.rolname IN ('anon', 'authenticated'))
        """)).all()
        # Effective checks also catch privileges inherited from another role.
        # Supabase browser roles need not exist on a plain local PostgreSQL.
        effective_grants = connection.execute(text("""
            SELECT c.relname, r.rolname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            CROSS JOIN pg_roles AS r
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                AND r.rolname IN ('anon', 'authenticated')
                AND has_table_privilege(
                    r.oid, c.oid,
                    'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
                )
        """)).all()
    assert [tuple(row) for row in grants if row.relname in APPLICATION_TABLES] == []
    assert [tuple(row) for row in effective_grants if row.relname in APPLICATION_TABLES] == []
