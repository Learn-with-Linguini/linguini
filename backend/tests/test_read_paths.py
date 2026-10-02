"""Read-path latency guarantees: no user write lock and bounded query counts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from test_postgres_sessions import age_session, analyze, create_run
from test_postgres_sessions import database as database

from app.repositories.postgres.users import users
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.base import utc_now


def test_active_read_does_not_wait_on_user_write_lock(database):
    engine, owner, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    repository = PostgresWorkflowRepository(engine, owner.id)
    lock = engine.connect()
    lock.begin()
    lock.execute(select(users.c.id).where(users.c.id == owner.id).with_for_update())
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(repository.active, profile.id).result(timeout=10)
        assert result is not None and result.session.id == UUID(sid)
    finally:
        lock.rollback()
        lock.close()


def test_active_read_reaps_stale_but_not_fresh_analysis(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    age_session(engine, UUID(sid), "analyzingScene", utc_now() - timedelta(minutes=30))
    assert client.get("/api/v1/sessions/active").json() is None
    second = create_run(client, profile, "fresh-session-key")["session"]["id"]
    age_session(engine, UUID(second), "analyzingScene", utc_now())
    active = client.get("/api/v1/sessions/active").json()
    assert active["session"]["id"] == second


def count_statements(engine, fn):
    statements = []

    def listener(_conn, _cursor, statement, _params, _context, _executemany):
        if not statement.startswith(("SET", "BEGIN", "COMMIT", "ROLLBACK", "SELECT 1")):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", listener)
    try:
        return fn(), statements
    finally:
        event.remove(engine, "before_cursor_execute", listener)


def count_request_statements(fn):
    """Records statements on every engine, including the one create_app() builds."""
    statements = []

    def listener(_conn, _cursor, statement, _params, _context, _executemany):
        if not statement.startswith(("SET", "BEGIN", "COMMIT", "ROLLBACK", "SELECT 1")):
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", listener)
    try:
        return fn(), statements
    finally:
        event.remove(Engine, "before_cursor_execute", listener)


def test_request_statement_counts(database):
    _, _, _, client = database
    for path, limit in [
        ("/api/v1/me", 1),
        ("/api/v1/me/progress", 4),
        ("/api/v1/journals", 6),
        ("/api/v1/preloaded-scenes", 3),
    ]:
        _, statements = count_request_statements(lambda path=path: client.get(path))
        assert len(statements) <= limit, (path, len(statements), statements)


def test_session_detail_query_count(database):
    engine, _, profile, client = database
    sid = create_run(client, profile)["session"]["id"]
    detail = analyze(client, sid)
    repository = PostgresWorkflowRepository(engine, profile.user_id)

    loaded, statements = count_statements(engine, lambda: repository.get(UUID(sid), profile.id))
    assert loaded.session.id == UUID(sid)
    assert len(loaded.tasks) == len(detail["tasks"])
    assert {v.id for v in loaded.vocabulary} == {
        o.vocabulary_item_id for o in loaded.scene_objects if o.vocabulary_item_id
    }
    assert loaded.translations
    assert len(statements) <= 6, len(statements)

    for task in detail["tasks"]:
        assert client.post(f"/api/v1/tasks/{task['id']}/skip", json={}).status_code == 200
    assert client.post(f"/api/v1/sessions/{sid}/complete").status_code == 200
    draft_sid = create_run(client, profile, "draft-session-key")["session"]["id"]
    assert draft_sid != sid
    assert client.post(f"/api/v1/sessions/{draft_sid}/analyze").status_code == 200
    loaded, statements = count_statements(
        engine, lambda: repository.get(UUID(draft_sid), profile.id)
    )
    assert loaded.session.status in {"analyzingScene", "awaitingObjectReview"}
    assert loaded.scene_objects and loaded.scene_object_relations
    assert len(statements) <= 5, len(statements)
