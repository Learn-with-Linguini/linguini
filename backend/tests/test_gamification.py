"""Saved answer rewards, mission evidence, and opt-in daily rankings."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, update
from test_mission_m01_workflow import _answer_key, _attempt, _lesson
from test_mission_m06_workflow import _m06_for_language
from test_postgres_sessions import database as database
from test_preloaded_templates_workflow import curated as curated

from app.repositories.postgres.game_resources import (
    equip_appearance,
    game_resource_events,
    lock_resource_owner,
    resource_snapshot,
    reward_basil,
)
from app.repositories.postgres.gamification import (
    mission_batches,
    photo_identities,
    question_events,
)
from app.repositories.postgres.language_profiles import language_profiles
from app.repositories.postgres.media_assets import media_assets
from app.repositories.postgres.tasks import session_tasks
from app.repositories.postgres.users import users
from app.schemas.base import utc_now
from app.schemas.users import User
from app.services import mission_eligibility


@pytest.fixture(autouse=True)
def m01_only(monkeypatch):
    monkeypatch.setitem(mission_eligibility.IMPLEMENTED_MISSIONS, "A1", (("M01", "A1", 1),))


def test_vocabulary_first_answer_survives_changed_replay_and_concurrent_checks(curated):
    engine, owner, _profile, client, *_ = curated
    repo, _sid, detail = _lesson(curated)
    task = detail.tasks[0]
    question = task.public_content.questions[0]
    expected = _answer_key(engine, task.id)["correctOptionIds"][question.question_id]
    wrong = next(option.option_id for option in question.options if option.option_id != expected)
    first = repo.check_vocabulary_answer(task.id, question.question_id, wrong)
    assert not first.is_correct and first.basil_earned == 5
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: repo.check_vocabulary_answer(
                    task.id,
                    question.question_id,
                    expected,
                ),
                range(8),
            )
        )
    assert all(item.accepted_option_id == wrong and item.basil_earned == 5 for item in results)
    restored = client.get(f"/api/v1/tasks/{task.id}/vocabulary-checks").json()["checks"]
    assert restored[0]["acceptedOptionId"] == wrong
    assert restored[0]["basilEarned"] == 5
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == 5
        assert (
            len(
                c.execute(select(question_events).where(question_events.c.task_id == task.id)).all()
            )
            == 1
        )


@pytest.mark.parametrize("correct", [False, True])
def test_question_rewards_and_batch_submission_share_one_ledger(curated, correct):
    engine, _owner, profile, client, *_ = curated
    repo, sid, detail = _lesson(curated)
    task = detail.tasks[1]
    key = _answer_key(engine, task.id)["correctOptionIds"]
    answers = {}
    for question in task.public_content.questions:
        answer = (
            key[question.question_id]
            if correct
            else next(
                (
                    item.option_id
                    for item in question.options
                    if item.option_id != key[question.question_id]
                ),
                "a deliberately wrong sentence",
            )
        )
        checked = repo.check_lesson_answer(task.id, question.question_id, answer)
        assert checked.basil_earned == (10 if correct else 5)
        answers[question.question_id] = checked.answer
    count = len(answers)
    first = _attempt(client, task, answers)
    assert first.status_code == 200, first.text
    assert first.json()["basilEarned"] == count * (10 if correct else 5)
    assert _attempt(client, task, answers).json()["basilEarned"] == first.json()["basilEarned"]
    restored = repo.lesson_checks(task.id).checks
    assert len(restored) == count and all(
        item.basil_earned == (10 if correct else 5) for item in restored
    )
    batch = client.get(f"/api/v1/sessions/{sid}/mission-progress").json()[0]
    assert batch["status"] == ("ready" if correct else "review")
    assert batch["percent"] == (100 if correct else 90)
    summary = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").json()
    badge = next(item for item in summary["missions"] if item["missionId"] == "M01")
    assert badge["badgeLevel"] == ("Taster" if correct else None)
    assert summary["basil"]["lifetime"] == first.json()["basilEarned"]
    # A CEFR change keeps already earned badges for this learning profile.
    with engine.begin() as c:
        c.execute(
            update(language_profiles)
            .where(language_profiles.c.id == profile.id)
            .values(proficiency_level="A2")
        )
    changed = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").json()
    assert (
        next(item for item in changed["missions"] if item["missionId"] == "M01")["badgeLevel"]
        == badge["badgeLevel"]
    )


def test_skipped_and_preparing_missions_cannot_complete_or_award_badges(curated):
    _engine, _owner, profile, client, *_ = curated
    _repo, sid, detail = _lesson(curated)
    task = detail.tasks[1]
    assert client.post(f"/api/v1/tasks/{task.id}/skip", json={}).status_code == 200
    batch = client.get(f"/api/v1/sessions/{sid}/mission-progress").json()[0]
    assert batch["status"] == "review" and batch["percent"] < 100
    summary = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").json()
    assert summary["basil"]["lifetime"] == 0
    assert all(item["badgeLevel"] is None for item in summary["missions"])


def test_regenerated_question_cannot_reuse_an_old_answer_or_mint_more_rewards(curated):
    engine, owner, _profile, client, *_ = curated
    repo, _sid, detail = _lesson(curated)
    task = detail.tasks[0]
    question = task.public_content.questions[0]
    expected = _answer_key(engine, task.id)["correctOptionIds"][question.question_id]
    repo.check_vocabulary_answer(task.id, question.question_id, expected)
    content = task.public_content.model_dump(mode="json", by_alias=True)
    content["questions"][0]["prompt"] = "A new version of this question"
    with engine.begin() as c:
        c.execute(
            update(session_tasks)
            .where(session_tasks.c.id == task.id)
            .values(public_content=content)
        )
    assert client.get(f"/api/v1/tasks/{task.id}/vocabulary-checks").status_code == 409
    response = client.post(
        f"/api/v1/tasks/{task.id}/check-vocabulary-answer",
        json={
            "questionId": question.question_id,
            "optionId": expected,
        },
    )
    assert response.status_code == 409
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == 10


def test_foreign_profile_and_session_progress_are_not_exposed(curated, monkeypatch):
    engine, _owner, profile, client, *_ = curated
    _repo, sid, _detail = _lesson(curated)
    other = User(display_name="Other chef", auth_provider_id=str(uuid4()))
    with engine.begin() as c:
        c.execute(insert(users).values(**other.model_dump(by_alias=False)))
    monkeypatch.setenv("DEMO_USER_ID", str(other.id))
    assert client.get(f"/api/v1/sessions/{sid}/mission-progress").status_code == 404
    assert client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").status_code == 404
    with engine.begin() as c:
        c.execute(delete(users).where(users.c.id == other.id))


@pytest.mark.parametrize(
    "photos,scenarios,independent,expected",
    [
        (["same"] * 3, ["a", "b", "c"], True, "Taster"),
        (["a", "b", "c"], ["same"] * 3, True, "Taster"),
        (["a", "b", "c"], ["a", "b", "c"], False, "Taster"),
        (["a", "b", "c"], ["a", "b", "c"], True, "Cook"),
    ],
)
def test_cook_needs_variety_and_less_assistance(curated, photos, scenarios, independent, expected):
    engine, owner, profile, client, *_ = curated
    _repo, sid, _detail = _lesson(curated)
    with engine.begin() as c:
        for i in range(3):
            # Separate versions model separate recorded batches without inventing spoken evidence.
            c.execute(
                insert(mission_batches).values(
                    id=uuid4(),
                    user_id=owner.id,
                    language_profile_id=profile.id,
                    session_id=sid,
                    mission_id="M01",
                    practice_level="A1",
                    content_version=i + 1,
                    policy_version="mission-badges.v1",
                    successful=True,
                    lower_assistance=independent,
                    photo_identity=photos[i],
                    scenario_identity=scenarios[i],
                    evidence={},
                    created_at=utc_now(),
                )
            )
    summary = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").json()
    badge = next(item for item in summary["missions"] if item["missionId"] == "M01")
    assert badge["badgeLevel"] == expected
    assert all(
        item["badgeLevel"] not in {"Chef", "Head Chef", "Master"} for item in summary["missions"]
    )


def test_reuploaded_identical_photo_has_one_identity(curated):
    from app.repositories.postgres.gamification import _photo_identity

    engine, owner, _profile, _client, *_ = curated
    _repo, sid, detail = _lesson(curated)
    hashes = []
    asset_ids = []
    with engine.begin() as c:
        original = (
            c.execute(select(media_assets).where(media_assets.c.id == detail.media_asset.id))
            .mappings()
            .one()
        )
        for _ in range(2):
            aid = uuid4()
            asset_ids.append(aid)
            c.execute(
                insert(media_assets).values(
                    **{
                        **dict(original),
                        "id": aid,
                        "source": "userUpload",
                        "owner_user_id": owner.id,
                        "storage_key": str(uuid4()),
                    }
                )
            )
            c.execute(
                insert(photo_identities).values(
                    media_asset_id=aid,
                    user_id=owner.id,
                    content_hash="a" * 64,
                    created_at=utc_now(),
                )
            )
            hashes.append(_photo_identity(c, {"scene_media_asset_id": aid, "user_id": owner.id}))
        assert hashes[0] == hashes[1]
        c.execute(delete(media_assets).where(media_assets.c.id.in_(asset_ids)))


def test_leaderboard_includes_all_daily_earners_and_ties_do_not_use_wallet_balance(database):
    engine, owner, _profile, client = database
    others = [User(display_name=f"Chef {i}", auth_provider_id=str(uuid4())) for i in range(2)]
    with engine.begin() as c:
        c.execute(insert(users), [u.model_dump(by_alias=False) for u in others])
        for person, score in [(owner, 30), (others[0], 30), (others[1], 40)]:
            lock_resource_owner(c, person.id)
            reward_basil(c, person.id, "today", amount=score)
        equip_appearance(c, owner.id, "herb", uuid4())
    result = client.get("/api/v1/me/chef-of-the-day").json()
    assert result["currentRank"] == 2 and result["basilToNextRank"] == 11
    assert result["todayBasil"] == result["personalBest"] == 30
    assert [row["rank"] for row in result["top"]] == [1, 2, 2]
    assert set(result["top"][0]) == {"rank", "displayName", "basil", "avatar"}
    assert result["top"][0]["avatar"] == "farfalle"
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == 10
        c.execute(delete(users).where(users.c.id.in_([u.id for u in others])))


def test_daily_basil_and_personal_best_use_the_same_utc_boundary(database):
    engine, owner, _profile, client = database
    now = utc_now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with engine.begin() as c:
        lock_resource_owner(c, owner.id)
        reward_basil(c, owner.id, "previous-day", amount=50)
        c.execute(
            update(game_resource_events)
            .where(game_resource_events.c.user_id == owner.id)
            .values(created_at=today - timedelta(microseconds=1))
        )
        reward_basil(c, owner.id, "new-day", amount=10)
    result = client.get("/api/v1/me/chef-of-the-day").json()
    assert result["todayBasil"] == 10 and result["personalBest"] == 50
    totals = client.get("/api/v1/me/gamification").json()["basil"]
    assert totals["today"] == 10 and totals["lifetime"] == 60
    assert result["dayEndsAt"] == totals["dayEndsAt"]



def test_regenerated_mission_progress_does_not_count_an_old_question_result(curated):
    engine, owner, _profile, client, *_ = curated
    repo, sid, detail = _lesson(curated)
    task = detail.tasks[1]
    question = task.public_content.questions[0]
    expected = _answer_key(engine, task.id)["correctOptionIds"][question.question_id]
    assert repo.check_lesson_answer(task.id, question.question_id, expected).basil_earned == 10
    original = client.get(f"/api/v1/sessions/{sid}/mission-progress").json()[0]
    assert original["assessedQuestions"] == original["correctQuestions"] == 1
    content = task.public_content.model_dump(mode="json", by_alias=True)
    content["questions"][0]["prompt"] = "A different mission question"
    with engine.begin() as c:
        c.execute(update(session_tasks).where(session_tasks.c.id == task.id).values(
            public_content=content,
        ))
    response = client.get(f"/api/v1/sessions/{sid}/mission-progress")
    assert response.status_code == 200, response.text
    progress = response.json()[0]
    assert progress["assessedQuestions"] == progress["correctQuestions"] == 0
    assert progress["independentCorrect"] == progress["percent"] == 0
    assert progress["status"] == "inProgress"
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == 10


def test_removed_accepted_mission_question_returns_conflict_instead_of_crashing(curated):
    engine, owner, _profile, client, *_ = curated
    repo, _sid, detail = _lesson(curated)
    task = detail.tasks[1]
    question = task.public_content.questions[0]
    key = _answer_key(engine, task.id)
    expected = key["correctOptionIds"][question.question_id]
    repo.check_lesson_answer(task.id, question.question_id, expected)
    content = task.public_content.model_dump(mode="json", by_alias=True)
    content["questions"] = [item for item in content["questions"]
                            if item["questionId"] != question.question_id]
    key["questionEvaluations"] = [item for item in key["questionEvaluations"]
                                  if item["questionId"] != question.question_id]
    key["correctOptionIds"].pop(question.question_id)
    with engine.begin() as c:
        c.execute(update(session_tasks).where(session_tasks.c.id == task.id).values(
            public_content=content, answer_key=key,
        ))
    response = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
        "questionId": question.question_id, "answer": expected,
    })
    assert response.status_code == 409, response.text
    assert "question changed" in response.json()["detail"]["message"].lower()
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == 10


@pytest.mark.parametrize("changed_field", [
    "targetIds", "sceneObjectId", "evidenceType", "acceptedTextAnswers", "statementCorrect",
])
def test_private_assessment_changes_cannot_reuse_old_question_evidence(curated, changed_field):
    engine, owner, _profile, client, *_ = curated
    repo, sid, detail = _lesson(curated)
    task = detail.tasks[1]
    key = _answer_key(engine, task.id)
    for question in task.public_content.questions:
        checked = repo.check_lesson_answer(
            task.id, question.question_id, key["correctOptionIds"][question.question_id]
        )
        assert checked.is_correct and checked.basil_earned == 10
    questions = task.public_content.questions
    question = questions[0] if changed_field == "statementCorrect" else questions[-1]
    evaluation = next(item for item in key["questionEvaluations"]
                      if item["questionId"] == question.question_id)
    if changed_field == "targetIds":
        evaluation[changed_field].append(next(
            target for target in ("describe-location", "describe-colour", "name-object")
            if target not in evaluation[changed_field]
        ))
    elif changed_field == "sceneObjectId":
        evaluation[changed_field] = str(next(
            obj.id for obj in detail.scene_objects
            if str(obj.id) != evaluation.get(changed_field)
        ))
    elif changed_field == "evidenceType":
        evaluation[changed_field] = "production"
    elif changed_field == "acceptedTextAnswers":
        key.setdefault("acceptedTextAnswersByQuestion", {})[question.question_id] = [
            "a new accepted variant",
        ]
    else:
        statements = key.setdefault("statementCorrect", {})
        statements[question.question_id] = not statements.get(question.question_id, False)
    with engine.begin() as c:
        c.execute(update(session_tasks).where(session_tasks.c.id == task.id).values(answer_key=key))
        assert c.execute(select(session_tasks.c.public_content).where(
            session_tasks.c.id == task.id,
        )).scalar_one() == task.public_content.model_dump(mode="json", by_alias=True)
    response = client.get(f"/api/v1/sessions/{sid}/mission-progress")
    assert response.status_code == 200, response.text
    progress = response.json()[0]
    assert progress["assessedQuestions"] == progress["correctQuestions"] == len(questions) - 1
    assert progress["independentCorrect"] == len(questions) - 1
    changed = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
        "questionId": question.question_id,
        "answer": key["correctOptionIds"][question.question_id],
    })
    assert changed.status_code == 409, changed.text
    assert "question changed" in changed.json()["detail"]["message"].lower()
    unchanged = next(item for item in questions if item.question_id != question.question_id)
    restored = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
        "questionId": unchanged.question_id,
        "answer": key["correctOptionIds"][unchanged.question_id],
    })
    assert restored.status_code == 200, restored.text
    assert restored.json()["basilEarned"] == 10
    with engine.begin() as c:
        assert resource_snapshot(c, owner.id).basil_leaves == len(questions) * 10


def test_m06_correct_after_targeted_feedback_is_assisted_without_another_reward(curated):
    engine, owner, profile, client, *_ = curated
    _engine, _client, _repo, sid, detail = _m06_for_language(curated)
    tasks = [task for task in detail.tasks if task.public_content.mission_id == "M06"]
    accepted = client.post(
        f"/api/v1/tasks/{tasks[0].id}/mission-scenario", json={"action": "accept"}
    )
    assert accepted.status_code == 200, accepted.text
    question_count = 0
    for task in tasks:
        answers = _answer_key(engine, task.id)["correctOptionIds"]
        for question in task.public_content.questions:
            question_count += 1
            expected = answers[question.question_id]
            wrong = next(
                (option.option_id for option in question.options if option.option_id != expected),
                "a deliberately wrong sentence",
            )
            initial = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
                "questionId": question.question_id, "answer": wrong,
            })
            assert initial.status_code == 200, initial.text
            assert initial.json()["isCorrect"] is False
            assert initial.json()["feedback"]
            assert initial.json()["basilEarned"] == 5
            corrected = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
                "questionId": question.question_id, "answer": expected,
            })
            assert corrected.status_code == 200, corrected.text
            assert corrected.json()["isCorrect"] is True
            assert corrected.json()["outcome"]["assistanceUsed"] is True
            assert "hint" in corrected.json()["outcome"]["assistance"]
            assert corrected.json()["basilEarned"] == 5
            restored = client.get(f"/api/v1/tasks/{task.id}/lesson-checks").json()["checks"]
            assert restored[-1]["outcome"] == corrected.json()["outcome"]
            live = next(item for item in client.get(
                f"/api/v1/sessions/{sid}/mission-progress"
            ).json() if item["missionId"] == "M06")
            assert live["correctQuestions"] == question_count
            assert live["independentCorrect"] == 0
        submitted = _attempt(client, task, answers, key=f"m06-feedback:{task.id}")
        assert submitted.status_code == 200, submitted.text
        outcomes = submitted.json()["attempt"]["evaluationDetails"]["questionOutcomes"]
        assert all(item["outcome"] == "correct" and item["assistanceUsed"] for item in outcomes)
        assert all("hint" in item["assistance"] for item in outcomes)
        assert _attempt(client, task, answers, key=f"m06-feedback:{task.id}").status_code == 200
    batch = next(item for item in client.get(
        f"/api/v1/sessions/{sid}/mission-progress"
    ).json() if item["missionId"] == "M06")
    assert batch["assessedQuestions"] == batch["correctQuestions"] == question_count
    assert batch["independentCorrect"] == 0
    assert batch["status"] == "review" and batch["percent"] == 90
    assert "Answer 2 questions correctly without assistance." in batch["requirements"]
    summary = client.get(f"/api/v1/me/gamification?languageProfileId={profile.id}").json()
    badge = next(item for item in summary["missions"] if item["missionId"] == "M06")
    assert badge["badgeLevel"] is None and badge["successfulBatches"] == 0
    with engine.begin() as c:
        recorded = c.execute(select(mission_batches).where(
            mission_batches.c.session_id == sid, mission_batches.c.mission_id == "M06",
        )).mappings().one()
        assert recorded["successful"] is False and recorded["lower_assistance"] is False
        assert resource_snapshot(c, owner.id).basil_leaves == question_count * 5


def test_m06_audio_replay_keeps_the_missions_independence_rule(curated):
    engine, _client, _repo, sid, detail = _m06_for_language(curated)
    client = curated[3]
    task = next(task for task in detail.tasks if task.public_content.mission_id == "M06")
    assert client.post(
        f"/api/v1/tasks/{task.id}/mission-scenario", json={"action": "accept"}
    ).status_code == 200
    question = task.public_content.questions[0]
    replay = client.post(f"/api/v1/tasks/{task.id}/lesson-assistance", json={
        "questionId": question.question_id, "step": "replayAudio",
    })
    assert replay.status_code == 200, replay.text
    checked = client.post(f"/api/v1/tasks/{task.id}/check-lesson-answer", json={
        "questionId": question.question_id,
        "answer": _answer_key(engine, task.id)["correctOptionIds"][question.question_id],
    })
    assert checked.status_code == 200, checked.text
    assert checked.json()["outcome"]["assistance"] == ["audio"]
    assert checked.json()["outcome"]["assistanceUsed"] is False
    progress = next(item for item in client.get(
        f"/api/v1/sessions/{sid}/mission-progress"
    ).json() if item["missionId"] == "M06")
    assert progress["independentCorrect"] == 1
