"""Standalone games stay free without farming lesson or room rewards."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_ispy_games import confirmed_lesson, count, start
from test_ispy_games import repos as repos
from test_postgres_sessions import database as database
from test_postgres_sessions import upload_asset

from app.ai.features.ispy_guess import ISpyGuessResult
from app.repositories.postgres.game_resources import game_resource_events, resource_snapshot
from app.repositories.postgres.vocabulary import vocabulary_encounters
from app.repositories.postgres.xp import xp_events
from app.schemas.tasks import (
    SkipTaskRequest,
    SubmitMultipleChoiceAttemptRequest,
    SubmitTextAttemptRequest,
)


@pytest.mark.parametrize("correct_clue", [False, True])
def test_standalone_replays_do_not_charge_sauce_or_earn_basil(database, repos, correct_clue):
    engine, owner, _profile, _client = database
    workflow, games, profile, _translator, clues = repos
    asset = upload_asset(engine, owner)
    confirmed_lesson(workflow, profile, asset, "resource-lesson")
    with engine.begin() as connection:
        before = resource_snapshot(connection, owner.id)
    assert before.sauce.remaining == 9
    for index in range(3):
        game = workflow.get(start(games, profile, asset, f"resource-game-{index}").session.id)
        task = next(task for task in game.tasks if task.kind == "ispyRound")
        target = clues.payloads[-1]["objects"][0]["key"]
        option = next(option for option in task.public_content.options
                      if (str(option.scene_object_id) == target) == correct_clue)
        request = SubmitMultipleChoiceAttemptRequest(
            input_mode="multipleChoice", option_id=option.option_id,
            idempotency_key=f"game-answer-{index}",
        )
        first = workflow.task_action(task.id, "attempt", request)
        replay = workflow.task_action(task.id, "attempt", request)
        assert first.attempt.id == replay.attempt.id
        for description in game.tasks:
            if description.kind != "reflection":
                continue
            workflow.ispy_guess_generator = SimpleNamespace(
                guess=lambda *_args, _target=str(description.scene_object_id), **_kwargs:
                ISpyGuessResult(
                    guessed_object_key=_target, ambiguous=False,
                    alternative_object_keys=[], matched_evidence_keys=[],
                    contradicted_evidence_keys=[], feedback="Matches the clue.",
                ))
            answer = workflow.task_action(description.id, "attempt", SubmitTextAttemptRequest(
                input_mode="text", text="Es rojo.", idempotency_key=str(uuid4()),
            ))
            assert answer.attempt.is_correct is True
        current = workflow.get(game.session.id)
        for remaining in current.tasks:
            if remaining.status not in {"completed", "skipped"}:
                workflow.task_action(remaining.id, "skip", SkipTaskRequest())
        workflow.finish(game.session.id, profile.id)
        assert count(engine, xp_events, game.session.id) == 0
        assert count(engine, vocabulary_encounters, game.session.id) == 0
    with engine.begin() as connection:
        after = resource_snapshot(connection, owner.id)
        events = connection.execute(select(game_resource_events.c.kind).where(
            game_resource_events.c.user_id == owner.id,
        )).scalars().all()
    assert after == before
    assert events == ["sauceSpend"]
