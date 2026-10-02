from types import SimpleNamespace
from uuid import uuid4

from app.services.tasks import TaskService


def test_task_action_receives_the_ispy_guess_generator(monkeypatch):
    generator = object()
    user = SimpleNamespace(id=uuid4())
    captured = {}

    class Workflow:
        def __init__(self, engine, user_id, *, ispy_guess_generator=None):
            captured.update(
                engine=engine,
                user_id=user_id,
                ispy_guess_generator=ispy_guess_generator,
            )

        def task_action(self, task_id, action, request):
            return "saved"

    import app.repositories.postgres.workflow as workflow

    monkeypatch.setattr(workflow, "PostgresWorkflowRepository", Workflow)
    service = TaskService(
        repository=object(),
        users=SimpleNamespace(get_current_user=lambda: user),
        engine="engine",
        ispy_guess_generator=generator,
    )

    assert service.action(uuid4(), "attempt", object()) == "saved"
    assert captured == {
        "engine": "engine",
        "user_id": user.id,
        "ispy_guess_generator": generator,
    }
