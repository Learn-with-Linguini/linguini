"""Real persisted encounter parents, using the session API and task repository."""

from uuid import uuid4

from test_postgres_sessions import create_run

from app.repositories.postgres.tasks import PostgresTaskRepository
from app.schemas.tasks import SessionTask


def create_encounter_task(engine, client, profile):
    run = create_run(client, profile, str(uuid4()))["session"]
    task = SessionTask(
        session_id=run["id"],
        phase="learning",
        kind="grammarPractice",
        order_index=0,
        public_content={"kind": "grammarPractice", "prompt": "Choose", "options": ["uno", "dos"]},
    )
    return PostgresTaskRepository(engine).create_task(task, profile.user_id)
