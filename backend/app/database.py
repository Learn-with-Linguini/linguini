"""PostgreSQL connection lifecycle. Prisma migrations exclusively own DDL."""

import os

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def create_database_engine() -> Engine:
    raw_url = os.getenv("DATABASE_URL", "")
    if not raw_url:
        raise ValueError("DATABASE_URL is required. JSON persistence is no longer supported.")
    try:
        url = make_url(raw_url)
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError
        url = url.set(drivername="postgresql+psycopg")
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL must be a valid PostgreSQL connection URI.") from None
    if "pgbouncer" in url.query:
        raise ValueError(
            "Remove the Prisma-only pgbouncer parameter from DATABASE_URL. "
            "For Supabase, use the Session pooler URL on port 5432 with sslmode=require."
        )
    if url.host and url.host.endswith(".pooler.supabase.com") and url.port == 6543:
        raise ValueError(
            "DATABASE_URL uses the Supabase transaction pooler (6543). "
            "This backend expects the Session pooler URL on port 5432."
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_recycle=1800,
        pool_timeout=10,
        connect_args={"connect_timeout": 10},
        hide_parameters=True,
    )


def read_connection(engine: Engine) -> Connection:
    """Single-statement reads need no transaction; AUTOCOMMIT avoids BEGIN/ROLLBACK round trips."""
    return engine.connect().execution_options(isolation_level="AUTOCOMMIT")
