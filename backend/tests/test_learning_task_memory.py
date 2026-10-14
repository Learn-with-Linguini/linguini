"""Grammar-only history adaptation preserves the scene contract and cache privacy."""

import json
from copy import deepcopy

import pytest
from test_learning_task_service import (
    INPUT,
    FakeTextClient,
    LearningTaskResult,
    RecordingTracer,
    builder_question,
    config,
    enter_kwargs,
    raw_response,
    response_body,
    tasks,
)

from app.ai.cache import CacheScope, InMemoryCacheStore, ResultCache, TemplateSet
from app.ai.features.learning_tasks.prompt import (
    LEARNING_TASK_MEMORY_PROMPT_VERSION,
    LEARNING_TASK_MEMORY_SYSTEM_PROMPT,
    LEARNING_TASK_PROMPT_VERSION,
    LEARNING_TASK_SYSTEM_PROMPT,
)
from app.ai.features.learning_tasks.schemas import REQUIRED_TASK_FOCUS_ORDER, required_task_focuses
from app.ai.features.learning_tasks.service import LearningTaskService
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.ai.observability import NoOpAITracer


def history():
    return {
        "version": 1,
        "profile": {"sourceLanguage": "en", "targetLanguage": "fr", "proficiencyLevel": "A1"},
        "totals": {
            "sessionsCompleted": 2,
            "gradedAttempts": 5,
            "readingTasksCompleted": 3,
            "journalsCompleted": 1,
        },
        "words": [
            {
                "term": "tasse",
                "source": "cup",
                "seenCount": 4,
                "correctCount": 1,
                "incorrectCount": 2,
                "lastOutcome": "incorrect",
                "journalMentions": 1,
                "assistedJournalMentions": 1,
                "journalSelections": 2,
                "relevant": True,
            }
        ],
        "grammar": {
            focus: {"correctCount": 0, "incorrectCount": 1, "lastOutcome": "incorrect"}
            for focus in REQUIRED_TASK_FOCUS_ORDER
        },
        "journal": {
            "acceptedCorrections": {
                category: 1
                for category in (
                    "grammar",
                    "spelling",
                    "syntax",
                    "vocabulary",
                    "clarity",
                )
            }
        },
    }


def generated_body():
    return response_body(LearningTaskResult.model_validate(tasks()))


def service(client, cache=None, tracer=None):
    return LearningTaskService(
        client,
        config(max_retries=0),
        tracer=tracer or NoOpAITracer(),
        provider="openai",
        cache=cache,
    )


def test_absent_and_null_history_use_identical_v2_requests():
    client = FakeTextClient([generated_body(), generated_body()])
    generator = service(client)
    generator.generate(INPUT)
    generator.generate({**INPUT, "learnerHistory": None})
    first, second = client.requests
    assert first == second
    assert first.prompt_version == LEARNING_TASK_PROMPT_VERSION == "learning-tasks.v2"
    assert first.system_prompt == LEARNING_TASK_SYSTEM_PROMPT
    assert "learnerHistory" not in first.user_content


def test_old_template_path_still_reuses_without_a_provider_call():
    templates = TemplateSet(record=True)
    creator = FakeTextClient([generated_body()])
    expected = service(creator).generate(
        INPUT, templates=templates, cache_scope=CacheScope.public()
    )
    assert len(templates.recorded) == 1
    untouched = FakeTextClient([])
    generator = service(untouched)
    assert generator.generate(INPUT, templates=templates) == expected
    assert generator.generate({**INPUT, "learnerHistory": None}, templates=templates) == expected
    assert untouched.requests == [] and len(templates.recorded) == 1


def test_history_uses_distinct_prompt_and_same_response_schema_with_one_call():
    personal = {**INPUT, "learnerHistory": history()}
    before = deepcopy(personal)
    client = FakeTextClient([generated_body()])
    tracer = RecordingTracer()
    result = service(client, tracer=tracer).generate(
        personal, cache_scope=CacheScope.user("person:fr")
    )
    assert personal == before
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.prompt_version == LEARNING_TASK_MEMORY_PROMPT_VERSION
    assert request.system_prompt == LEARNING_TASK_MEMORY_SYSTEM_PROMPT
    assert request.system_prompt.startswith(LEARNING_TASK_SYSTEM_PROMPT)
    assert request.json_schema_name == "learning_tasks_v2"
    body = json.loads(request.user_content)
    assert body["learnerHistory"] == history()
    assert body["requiredTaskFocuses"] == list(required_task_focuses(INPUT))
    assert [task.focus for task in result.tasks] == list(required_task_focuses(INPUT))
    assert (
        enter_kwargs(tracer, "learning-task-generation")["prompt_version"] == request.prompt_version
    )
    traced_metadata = enter_kwargs(tracer, "learning-task-generation")["metadata"]
    assert "learnerHistory" not in traced_metadata


def test_personal_generation_neither_reuses_nor_records_shared_templates():
    templates = TemplateSet(record=True)
    generic = FakeTextClient([generated_body()])
    service(generic).generate(INPUT, templates=templates)
    old_templates = deepcopy(templates.content())
    templates.generate = False
    private = FakeTextClient([generated_body()])
    service(private).generate(
        {**INPUT, "learnerHistory": history()},
        cache_scope=CacheScope.user("person:fr"),
        templates=templates,
    )
    assert len(private.requests) == 1
    assert templates.content() == old_templates


def test_private_cache_reuses_identical_history_but_changed_history_misses():
    store = InMemoryCacheStore(10)
    cache = ResultCache(store)
    client = FakeTextClient([generated_body(), generated_body()])
    generator = service(client, cache)
    payload = {**INPUT, "learnerHistory": history()}
    private = CacheScope.user("person:fr")
    generator.generate(payload, cache_scope=private)
    generator.generate(deepcopy(payload), cache_scope=private)
    changed = deepcopy(payload)
    changed["learnerHistory"]["grammar"]["pluralNounForm"]["incorrectCount"] += 1
    generator.generate(changed, cache_scope=private)
    assert len(client.requests) == 2
    assert len(store._entries) == 2
    assert all(entry.scope == private for entry in store._entries.values())
    assert all(
        entry.provenance.prompt_version == LEARNING_TASK_MEMORY_PROMPT_VERSION
        for entry in store._entries.values()
    )


def test_personal_cache_is_isolated_by_profile_scope():
    store = InMemoryCacheStore(10)
    client = FakeTextClient([generated_body(), generated_body()])
    generator = service(client, ResultCache(store))
    payload = {**INPUT, "learnerHistory": history()}
    for scope in (CacheScope.user("person:profile-a"), CacheScope.user("person:profile-b")):
        generator.generate(payload, cache_scope=scope)
    assert len(client.requests) == 2 and len(store._entries) == 2


def test_public_scope_bypasses_personal_cache_and_cannot_record_a_template():
    store = InMemoryCacheStore(10)
    cache = ResultCache(store)
    client = FakeTextClient([generated_body(), generated_body(), generated_body()])
    generator = service(client, cache)
    generator.generate(INPUT, cache_scope=CacheScope.public())
    original = dict(store._entries)
    templates = TemplateSet(record=True)
    personal = {**INPUT, "learnerHistory": history()}
    generator.generate(personal, cache_scope=CacheScope.public(), templates=templates)
    generator.generate(personal, cache_scope=CacheScope.public(), templates=templates)
    assert len(client.requests) == 3
    assert store._entries == original
    assert templates.recorded == []
    assert all(
        entry.provenance.prompt_version == LEARNING_TASK_PROMPT_VERSION
        for entry in store._entries.values()
    )


@pytest.mark.parametrize("invalid", [[], "journal prose", {"version": 2}, {"version": 1}])
def test_malformed_history_is_rejected_before_any_provider_or_cache_call(invalid):
    store = InMemoryCacheStore(10)
    client = FakeTextClient([])
    with pytest.raises(LearningTaskGenerationError):
        service(client, ResultCache(store)).generate(
            {**INPUT, "learnerHistory": invalid}, cache_scope=CacheScope.public()
        )
    assert client.requests == [] and store._entries == {}


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.update(userId="private-id"),
        lambda data: data.update(version=True),
        lambda data: data["journal"].update(text="private journal writing"),
        lambda data: data["words"][0].update(answerText="private submitted answer"),
        lambda data: data["grammar"]["sceneDescription"].update(taskId="private-task-id"),
        lambda data: data["profile"].update(userId="private-profile-owner"),
        lambda data: data["journal"]["acceptedCorrections"].update(arbitrary="free text"),
        lambda data: data["words"].extend([deepcopy(data["words"][0])] * 16),
        lambda data: data["words"][0].update(incorrectCount=-1),
        lambda data: data["words"][0].update(term="a" * 65),
        lambda data: data["words"][0].update(lastOutcome="mastered"),
        lambda data: data["profile"].update(targetLanguage="es"),
    ],
)
def test_history_boundary_rejects_prose_identifiers_unbounded_words_and_language_mismatch(change):
    data = history()
    change(data)
    client = FakeTextClient([])
    with pytest.raises(LearningTaskGenerationError):
        service(client).generate({**INPUT, "learnerHistory": data})
    assert client.requests == []


def test_old_words_do_not_expand_current_scene_grounding_enums():
    data = history()
    data["words"][0].update(term="chien", source="dog", relevant=False)
    output = tasks()
    output["tasks"][0]["questions"][0]["objectKeys"] = ["old-dog-object"]
    client = FakeTextClient([raw_response(output)])
    with pytest.raises(LearningTaskGenerationError):
        service(client).generate({**INPUT, "learnerHistory": data})
    request = client.requests[0]
    schema = json.dumps(request.json_schema)
    assert "old-dog-object" not in schema and '"chien"' not in schema
    assert len(client.requests) == 1


def test_historical_weak_focus_cannot_restore_a_task_without_current_relationships():
    data = history()
    data["grammar"]["sceneDescription"]["incorrectCount"] = 100
    current = {**INPUT, "relationships": [], "learnerHistory": data}
    output = tasks()
    output["tasks"] = [task for task in output["tasks"] if task["focus"] != "sceneDescription"]
    output["tasks"][-1]["questions"] = [
        builder_question("build-1", relation=False),
        builder_question("build-2", relation=False),
    ]
    client = FakeTextClient([raw_response(output)])
    result = service(client).generate(current)
    expected = ["genderNumberAgreement", "pluralNounForm", "chainedDescription"]
    assert [task.focus for task in result.tasks] == expected
    assert json.loads(client.requests[0].user_content)["requiredTaskFocuses"] == expected
    assert all(
        not question.relationship_keys for task in result.tasks for question in task.questions
    )


def test_memory_guidance_keeps_exposure_and_corrections_separate_from_independent_mastery():
    prompt = LEARNING_TASK_MEMORY_SYSTEM_PROMPT
    assert "seenCount" in prompt
    assert all(
        field in prompt
        for field in ("journalMentions", "assistedJournalMentions", "journalSelections")
    )
    assert "a user-written or edited revision can retain previously assisted prose" in prompt
    assert "none establishes independent production, recall, or mastery" in prompt
    assert "vocabulary was saved from earlier approved photos" in prompt
    assert "not necessarily times a card was viewed or the word recalled" in prompt
    assert "accepted assistance, not a test passed independently" in prompt
    assert "two-to-four-question bounds" in prompt
    assert "every required focus in the original order" in prompt
    assert "must not appear as new exercise vocabulary or scene facts" in prompt


def test_history_size_limit_counts_utf8_bytes_before_cache_or_provider():
    data = history()
    for count in range(1, 17):
        data["words"] = [
            {**history()["words"][0], "term": "é" * 64, "source": "è" * 64} for _ in range(count)
        ]
        encoded = json.dumps(data, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 6 * 1024:
            break
    assert len(encoded) <= 6 * 1024 < len(encoded.encode("utf-8"))
    store = InMemoryCacheStore(10)
    client = FakeTextClient([])
    with pytest.raises(LearningTaskGenerationError, match="summary size limit"):
        service(client, ResultCache(store)).generate(
            {**INPUT, "learnerHistory": data},
            cache_scope=CacheScope.public(),
        )
    assert client.requests == [] and store._entries == {}


def test_history_under_utf8_limit_and_matching_profile_generates_normally():
    data = history()
    data["words"][0].update(term="tassé", source="café")
    client = FakeTextClient([generated_body()])
    service(client).generate(
        {
            **INPUT,
            "sourceLanguage": "EN",
            "proficiencyLevel": "a1",
            "learnerHistory": data,
        }
    )
    assert len(client.requests) == 1
    assert json.loads(client.requests[0].user_content)["learnerHistory"] == data


@pytest.mark.parametrize(
    "expected",
    [
        {"sourceLanguage": "es"},
        {"sourceLanguage": None},
        {"proficiencyLevel": "A2"},
        {"proficiencyLevel": None},
    ],
)
def test_supplied_source_language_and_level_must_match_history(expected):
    client = FakeTextClient([])
    with pytest.raises(LearningTaskGenerationError, match="current learning profile"):
        service(client).generate({**INPUT, **expected, "learnerHistory": history()})
    assert client.requests == []


def test_no_history_keeps_v2_behavior_even_with_supplied_profile_fields():
    current = {**INPUT, "sourceLanguage": "es", "proficiencyLevel": "A2"}
    client = FakeTextClient([generated_body(), generated_body()])
    generator = service(client)
    generator.generate(current)
    generator.generate({**current, "learnerHistory": None})
    assert client.requests[0] == client.requests[1]
    assert client.requests[0].system_prompt == LEARNING_TASK_SYSTEM_PROMPT
