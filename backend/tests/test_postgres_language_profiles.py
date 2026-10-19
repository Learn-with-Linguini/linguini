"""Language-profile checks against a migrated, dedicated test PostgreSQL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import create_database_engine
from app.main import create_app
from app.repositories.language_profiles import (
    LanguageProfileConflictError,
    LanguageProfileNotFoundError,
    LanguageProfileStorageError,
)
from app.repositories.postgres.language_profiles import (
    PostgresLanguageProfileRepository,
    language_profiles,
)
from app.repositories.postgres.users import users
from app.schemas.enums import ProficiencyLevel
from app.schemas.users import LanguageProfile, UpdateLanguageProfileRequest, User


def profile(user_id, language="es", **kwargs):
    return LanguageProfile(
        user_id=user_id,
        source_language_code="en",
        target_language_code=language,
        proficiency_level="A1",
        daily_goal_minutes=10,
        **kwargs,
    )


def test_storage_errors_are_wrapped():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("select", {}, Exception("private detail"))
    engine.begin.side_effect = OperationalError("update", {}, Exception("private detail"))
    repository = PostgresLanguageProfileRepository(engine)
    with pytest.raises(LanguageProfileStorageError):
        repository.list_for_user(uuid4())
    with pytest.raises(LanguageProfileStorageError):
        repository.create(profile(uuid4()))
    with pytest.raises(LanguageProfileStorageError):
        repository.update(uuid4(), uuid4(), UpdateLanguageProfileRequest(is_active=True))


@pytest.fixture
def database(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Requires migrated test PostgreSQL")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    engine = create_database_engine()
    owners = [User(auth_provider_id=f"test-{uuid4()}", display_name="Test") for _ in range(2)]
    monkeypatch.setenv("DEMO_USER_ID", str(owners[0].id))
    with engine.begin() as connection:
        for owner in owners:
            connection.execute(insert(users).values(**owner.model_dump(by_alias=False)))
    try:
        yield engine, owners
    finally:
        with engine.begin() as connection:
            connection.execute(delete(users).where(users.c.id.in_([owner.id for owner in owners])))
        engine.dispose()


def test_profile_api_switching_and_isolation(database):
    engine, owners = database
    repository = PostgresLanguageProfileRepository(engine)
    spanish = repository.create(profile(owners[0].id))
    other = repository.create(profile(owners[1].id))
    with TestClient(create_app()) as client:
        assert len(client.get("/api/v1/preloaded-scenes").json()) == 6
        response = client.post(
            "/api/v1/me/language-profiles",
            json={
                "sourceLanguageCode": "en",
                "targetLanguageCode": "fr",
                "proficiencyLevel": "B1",
            },
        )
        assert response.status_code == 201
        french = response.json()
        scenes = client.get("/api/v1/preloaded-scenes").json()
        assert len(scenes) == 6 and all("languageCode" not in row for row in scenes)
        assert client.get("/api/v1/me/vocabulary").json()["items"] == []
        rows = client.get("/api/v1/me/language-profiles").json()
        assert len(rows) == 2 and sum(row["isActive"] for row in rows) == 1
        assert (
            client.patch(
                f"/api/v1/me/language-profiles/{other.id}", json={"isActive": True}
            ).status_code
            == 404
        )
        url = f"/api/v1/me/language-profiles/{spanish.id}"
        response = client.patch(url, json={"isActive": True, "dailyGoalMinutes": None})
        updated = LanguageProfile.model_validate(response.json())
        assert updated.daily_goal_minutes is None
        assert updated.created_at == spanish.created_at
        assert updated.updated_at > spanish.updated_at
        assert len(client.get("/api/v1/preloaded-scenes").json()) == 6
        assert client.patch(url, json={"dailyGoalMinutes": 0}).status_code == 422
        assert client.patch(url, json={"isActive": False}).status_code == 200
        assert client.get("/api/v1/preloaded-scenes").status_code == 200
        assert (
            client.patch(
                f"/api/v1/me/language-profiles/{french['id']}", json={"isActive": True}
            ).status_code
            == 200
        )
    assert repository.list_for_user(owners[1].id)[0].is_active


def test_duplicate_rollback_and_missing(database):
    engine, owners = database
    repository = PostgresLanguageProfileRepository(engine)
    repository.create(profile(owners[0].id))
    french = repository.create(profile(owners[0].id, "fr"))
    with pytest.raises(LanguageProfileConflictError):
        repository.create(profile(owners[0].id, "ES"))
    assert (
        next(row for row in repository.list_for_user(owners[0].id) if row.is_active).id == french.id
    )
    with pytest.raises(LanguageProfileNotFoundError):
        repository.update(owners[0].id, uuid4(), UpdateLanguageProfileRequest(is_active=True))


def test_concurrent_activation(database):
    engine, owners = database
    repository = PostgresLanguageProfileRepository(engine)
    spanish = repository.create(profile(owners[0].id))
    french = repository.create(profile(owners[0].id, "fr"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda row: repository.update(
                    owners[0].id, row.id, UpdateLanguageProfileRequest(is_active=True)
                ),
                [spanish, french],
            )
        )
    assert sum(row.is_active for row in repository.list_for_user(owners[0].id)) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"daily_goal_minutes": 241},
        {"proficiency_level": "D1"},
        {"proficiency_level": "A3"},
        {"preferred_input_mode": "voice"},
        {"target_language_code": "EN"},
        {"target_language_code": "invalid_code"},
        {"user_id": uuid4()},
    ],
)
def test_database_constraints(database, patch):
    engine, owners = database
    values = profile(owners[0].id).model_dump(by_alias=False) | patch
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(insert(language_profiles).values(**values))


def test_database_active_constraint_and_cascade(database):
    engine, owners = database
    repository = PostgresLanguageProfileRepository(engine)
    repository.create(profile(owners[0].id))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(language_profiles).values(
                **profile(owners[0].id, "fr").model_dump(by_alias=False)
            )
        )
    with engine.begin() as connection:
        connection.execute(delete(users).where(users.c.id == owners[0].id))
    assert repository.list_for_user(owners[0].id) == []


def test_pre_a1_profile_is_stored_as_a0(database):
    engine, owners = database
    repository = PostgresLanguageProfileRepository(engine)
    created = repository.create(
        profile(owners[0].id).model_copy(update={"proficiency_level": ProficiencyLevel.A0})
    )
    assert [row.proficiency_level for row in repository.list_for_user(owners[0].id)] == ["A0"]
    updated = repository.update(
        owners[0].id, created.id, UpdateLanguageProfileRequest(proficiency_level="A1")
    )
    assert updated.proficiency_level == "A1"


def test_pre_a1_migration_allows_a0_levels_only_in_isolated_tables(database):
    engine, _ = database
    schema = "pre_a1_test_" + uuid4().hex
    migration = (Path(__file__).parents[1] / "prisma" / "migrations"
                 / "20261015000000_pre_a1_level" / "migration.sql").read_text()
    sql = "\n".join(line for line in migration.splitlines() if not line.startswith("--"))
    sql = sql.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
    for table in ("language_profiles", "vocabulary_items"):
        sql = sql.replace(f"public.{table}", f"{schema}.{table}")
    levels = {
        "language_profiles": ("proficiency_level", "language_profiles_level"),
        "vocabulary_items": ("difficulty_level", "vocabulary_items_difficulty_level_check"),
    }
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
            for table, (column, constraint) in levels.items():
                connection.exec_driver_sql(
                    f"CREATE TABLE {schema}.{table} ({column} VARCHAR(2) CONSTRAINT {constraint} "
                    f"CHECK ({column} IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')))"
                )
                connection.exec_driver_sql(f"INSERT INTO {schema}.{table} VALUES ('B2')")
            connection.exec_driver_sql(sql)
            for table, (column, _) in levels.items():
                connection.exec_driver_sql(f"INSERT INTO {schema}.{table} VALUES ('A0')")
                assert connection.execute(text(
                    f"SELECT {column} FROM {schema}.{table} ORDER BY {column}"
                )).scalars().all() == ["A0", "B2"]
        for table in levels:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.exec_driver_sql(f"INSERT INTO {schema}.{table} VALUES ('A3')")
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
