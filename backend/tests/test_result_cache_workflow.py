"""Task generation passes a public cache scope only for unchanged curated content."""

from types import SimpleNamespace
from uuid import UUID, uuid4

from test_postgres_sessions import create_run
from test_postgres_sessions import database as database

from app.ai.cache import CacheScope
from app.ai.features.translation import SceneTranslationError
from app.repositories.postgres.workflow import PostgresWorkflowRepository
from app.schemas.sessions import ReviewPracticeRequest


def test_curated_reviews_share_and_learner_edits_stay_private(database):
    engine, owner, profile, client = database
    scopes = []

    def translate(_payload, cache_scope=None):
        scopes.append(cache_scope)
        raise SceneTranslationError("off")

    repo = PostgresWorkflowRepository(
        engine, owner.id, translator=SimpleNamespace(translate=translate)
    )

    def review(key, **changes):
        sid = UUID(create_run(client, profile, key=key)["session"]["id"])
        repo.analyze(sid, profile.id)
        objects = repo.get(sid, profile.id).scene_objects
        repo.review(
            sid,
            profile.id,
            ReviewPracticeRequest.model_validate(
                {"acceptedObjectIds": [str(objects[0].id)], **changes}
            ),
        )

    review("curated-review")
    review(
        "edited-review",
        addedObjects=[{"id": str(uuid4()), "label": "my diary", "x": 0.5, "y": 0.5}],
    )
    assert scopes == [CacheScope.public(), CacheScope.user(owner.id)]
