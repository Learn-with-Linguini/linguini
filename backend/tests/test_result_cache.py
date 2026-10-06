"""Validated-result cache: keys, scopes, remapping, invalidation, single-flight."""

import json
import threading
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4, uuid5

import pytest

from app.ai.cache import (
    CacheRequest,
    CacheScope,
    CacheWaitTimeout,
    FeatureVersion,
    Generated,
    InMemoryCacheStore,
    ReferenceMap,
    ResultCache,
)
from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.ispy_clues import ISpyClueService
from app.ai.features.translation import SceneTranslationError, SceneTranslationService
from app.ai.observability import NoOpAITracer
from app.ai.settings import AiConfigurationError, load_ai_settings
from app.repositories.postgres.workflow import is_curated_content
from app.schemas.media import SceneObject, SceneObjectRelation

PUBLIC = CacheScope.public()
VERSION = FeatureVersion("feature", "prompt.v1", "schema.v1", "validator.v1")


class FakeClient:
    """Text client returning queued outputs; optionally blocks until released."""

    def __init__(self, outputs, release=None):
        self.outputs = list(outputs)
        self.calls = 0
        self.release = release
        self.started = threading.Event()
        self._lock = threading.Lock()

    def generate(self, request):
        with self._lock:
            self.calls += 1
            outcome = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        self.started.set()
        if self.release is not None:
            self.release.wait(5)
        if isinstance(outcome, Exception):
            raise outcome
        return TextModelResponse(
            output_text=outcome(request) if callable(outcome) else outcome,
            model_name="test-model",
            prompt_version=request.prompt_version,
        )


def config(**overrides):
    return TextModelConfig(**{"model_name": "test-model", "max_retries": 1, **overrides})


def translator(client, cache, **overrides):
    return SceneTranslationService(
        client, config(**overrides), tracer=NoOpAITracer(), provider="openai", cache=cache
    )


def scene(chair, table, relation):
    return {
        "targetLanguage": "es",
        "sceneTitle": "Kitchen",
        "sceneSummary": "A kitchen.",
        "objects": [{"key": chair, "source": "chair"}, {"key": table, "source": "table"}],
        "attributes": [{"key": f"{chair}:color", "source": "red"}],
        "relationships": [{"key": relation, "source": "next_to"}],
    }


def translation_output(request):
    """Echo the request's keys back with fixed Spanish translations."""
    payload = json.loads(request.user_content.split("\n")[0])
    words = {"chair": ("silla", "la", "feminine"), "table": ("mesa", "la", "feminine")}
    return json.dumps({
        "objects": [
            {"key": row["key"], "source": row["source"], "translation": words[row["source"]][0],
             "article": words[row["source"]][1], "gender": words[row["source"]][2]}
            for row in payload["objects"]
        ],
        "attributes": [
            {"key": row["key"], "source": row["source"], "translation": "rojo",
             "article": None, "gender": None}
            for row in payload["attributes"]
        ],
        "relationships": [
            {"key": row["key"], "source": row["source"], "translation": "junto a",
             "article": None, "gender": None}
            for row in payload["relationships"]
        ],
    })


def ids(count=3):
    return [str(uuid4()) for _ in range(count)]


def test_valid_hit_makes_no_provider_call_and_uses_current_ids():
    cache = ResultCache()
    client = FakeClient([translation_output])
    service = translator(client, cache)
    first = service.translate(scene(*ids()), cache_scope=PUBLIC)
    current = ids()
    second = service.translate(scene(*current), cache_scope=PUBLIC)

    assert client.calls == 1
    assert {row.key for row in second.objects} == set(current[:2])
    assert second.attributes[0].key == f"{current[0]}:color"
    assert second.relationships[0].key == current[2]
    assert [row.translation for row in second.objects] == [
        row.translation for row in first.objects
    ]


def test_scopes_isolate_users_and_public_content():
    cache = ResultCache()
    client = FakeClient([translation_output])
    service = translator(client, cache)
    payload = scene(*ids())
    for scope in (CacheScope.user("a"), CacheScope.user("b"), PUBLIC, CacheScope.user("a")):
        service.translate(payload, cache_scope=scope)
    assert client.calls == 3


def test_bypass_and_disabled_cache_always_call_the_provider():
    client = FakeClient([translation_output])
    payload = scene(*ids())
    cached = translator(client, ResultCache())
    cached.translate(payload, cache_scope=None)
    cached.translate(payload, cache_scope=None)
    disabled = translator(client, ResultCache(enabled=False))
    disabled.translate(payload, cache_scope=PUBLIC)
    disabled.translate(payload, cache_scope=PUBLIC)
    assert client.calls == 4


def test_failures_and_invalid_output_are_never_cached():
    payload = scene(*ids())
    cache = ResultCache()
    failing = FakeClient([ProviderError(ProviderErrorCode.PROVIDER_REFUSED, "refused")])
    with pytest.raises(SceneTranslationError):
        translator(failing, cache).translate(payload, cache_scope=PUBLIC)
    invalid = FakeClient(["not json"])
    with pytest.raises(SceneTranslationError):
        translator(invalid, cache).translate(payload, cache_scope=PUBLIC)
    assert invalid.calls == 2

    valid = FakeClient([translation_output])
    translator(valid, cache).translate(payload, cache_scope=PUBLIC)
    assert valid.calls == 1


def test_generation_settings_and_versions_are_part_of_the_key():
    cache = ResultCache()
    client = FakeClient([translation_output])
    payload = scene(*ids())
    translator(client, cache).translate(payload, cache_scope=PUBLIC)
    translator(client, cache, temperature=0.7).translate(payload, cache_scope=PUBLIC)
    translator(client, cache, model_name="other").translate(payload, cache_scope=PUBLIC)
    assert client.calls == 3

    calls = []
    request = direct_request(calls)
    cache.get_or_generate(request)
    cache.get_or_generate(replace(request, version=replace(VERSION, validator_version="v2")))
    assert len(calls) == 2


def test_changed_content_misses():
    cache = ResultCache()
    client = FakeClient([translation_output])
    service = translator(client, cache)
    payload = scene(*ids())
    service.translate(payload, cache_scope=PUBLIC)
    service.translate({**payload, "sceneSummary": "Another kitchen."}, cache_scope=PUBLIC)
    service.translate({**payload, "targetLanguage": "fr"}, cache_scope=PUBLIC)
    assert client.calls == 3


def test_entry_with_unknown_reference_fails_revalidation_and_is_dropped():
    store = InMemoryCacheStore(10)
    cache = ResultCache(store)
    client = FakeClient([translation_output])
    service = translator(client, cache)
    service.translate(scene(*ids()), cache_scope=PUBLIC)
    ((key, entry),) = store._entries.items()
    store.put(key, replace(entry, value=entry.value.replace('"o2"', '"o9"')))

    result = service.translate(scene(*ids()), cache_scope=PUBLIC)
    assert client.calls == 2
    assert all(not row.key.startswith("o") for row in result.objects)
    assert '"o2"' in store.get(key).value


def test_results_from_unapproved_deployments_are_rejected():
    calls = []
    cache = ResultCache()
    request = direct_request(calls, approved={"a", "b"}, served="a")
    cache.get_or_generate(request)
    cache.get_or_generate(request)
    assert len(calls) == 1
    cache.get_or_generate(replace(request, approved_deployments=frozenset({"b"})))
    assert len(calls) == 2


def test_results_served_outside_the_route_are_not_stored():
    calls = []
    cache = ResultCache()
    request = direct_request(calls, approved={"a"}, served=None)
    cache.get_or_generate(request)
    cache.get_or_generate(request)
    assert len(calls) == 2


def test_results_with_unknown_references_are_not_stored():
    calls = []
    cache = ResultCache()
    request = direct_request(calls, result={"key": "session-specific"})
    cache.get_or_generate(request)
    cache.get_or_generate(request)
    assert len(calls) == 2


def test_invalidation_by_feature_scope_and_all():
    cache = ResultCache()
    calls = []
    alice, bob = CacheScope.user("alice"), CacheScope.user("bob")
    requests = {
        (feature, scope): direct_request(
            calls, version=replace(VERSION, feature=feature), scope=scope
        )
        for feature in ("translation", "clues")
        for scope in (alice, bob)
    }
    for request in requests.values():
        cache.get_or_generate(request)
    assert len(calls) == 4

    assert cache.invalidate(scope=alice) == 2
    assert cache.invalidate(feature="clues") == 1
    for request in requests.values():
        cache.get_or_generate(request)
    assert len(calls) == 7
    assert cache.clear() == 4


def test_ttl_expiry_and_capacity_eviction():
    now = [0.0]
    cache = ResultCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    calls = []
    first = direct_request(calls, payload={"objects": [{"key": "x", "source": "1"}]})
    second = direct_request(calls, payload={"objects": [{"key": "x", "source": "2"}]})
    third = direct_request(calls, payload={"objects": [{"key": "x", "source": "3"}]})
    cache.get_or_generate(first)
    now[0] = 9.9
    cache.get_or_generate(first)
    assert len(calls) == 1
    now[0] = 10
    cache.get_or_generate(first)
    assert len(calls) == 2

    cache.get_or_generate(second)
    cache.get_or_generate(first)
    cache.get_or_generate(third)
    cache.get_or_generate(first)
    assert len(calls) == 4
    cache.get_or_generate(second)
    assert len(calls) == 5


class SharedCounter:
    """Tracer counting requests that joined another request's generation."""

    def __init__(self):
        self.shared = 0
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name, *, metadata=None):
        counter = self

        class Observation:
            def update(self, **fields):
                if (fields.get("metadata") or {}).get("outcome") == "shared":
                    with counter._lock:
                        counter.shared += 1

        yield Observation()


def run_concurrently(count, target):
    results, errors = [], []

    def run():
        try:
            results.append(target())
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(count)]
    return threads, results, errors


def wait_for(condition):
    event = threading.Event()
    for _ in range(500):
        if condition():
            return
        event.wait(0.01)
    raise AssertionError("condition not reached")


def test_concurrent_misses_share_one_provider_call():
    tracer = SharedCounter()
    cache = ResultCache(tracer=tracer)
    release = threading.Event()
    client = FakeClient([translation_output], release=release)
    service = translator(client, cache)
    payloads = [scene(*ids()) for _ in range(6)]
    leader, results, errors = run_concurrently(1, lambda: service.translate(
        payloads[0], cache_scope=PUBLIC
    ))
    leader[0].start()
    client.started.wait(5)
    followers = [
        threading.Thread(
            target=lambda p=p: results.append(service.translate(p, cache_scope=PUBLIC))
        )
        for p in payloads[1:]
    ]
    for thread in followers:
        thread.start()
    wait_for(lambda: tracer.shared == 5)
    release.set()
    for thread in [*leader, *followers]:
        thread.join(5)

    assert errors == []
    assert client.calls == 1
    assert len(results) == 6
    assert cache.in_flight == 0
    for payload in payloads:
        assert any(
            {row.key for row in result.objects} == {row["key"] for row in payload["objects"]}
            for result in results
        )


def test_waiters_share_the_first_calls_failure_and_cleanup_runs():
    tracer = SharedCounter()
    cache = ResultCache(tracer=tracer)
    release = threading.Event()
    calls = []

    def failing():
        calls.append(1)
        release.wait(5)
        raise RuntimeError("provider down")

    request = direct_request(calls, compute=failing)
    threads, results, errors = run_concurrently(4, lambda: cache.get_or_generate(request))
    threads[0].start()
    wait_for(lambda: cache.in_flight == 1)
    for thread in threads[1:]:
        thread.start()
    wait_for(lambda: tracer.shared == 3)
    release.set()
    for thread in threads:
        thread.join(5)

    assert len(calls) == 1
    assert len(errors) == 4 and results == []
    assert all(str(error) == "provider down" for error in errors)
    assert cache.in_flight == 0
    release.clear()
    later = []
    cache.get_or_generate(direct_request(later))
    assert len(later) == 1


def test_waiter_times_out_when_the_first_call_overruns():
    cache = ResultCache()
    release = threading.Event()
    calls = []

    def slow():
        calls.append(1)
        release.wait(5)
        return Generated({"value": 1}, "a", "m")

    request = direct_request(calls, compute=slow, wait_seconds=0.05)
    leader = threading.Thread(target=lambda: cache.get_or_generate(request))
    leader.start()
    wait_for(lambda: cache.in_flight == 1)
    with pytest.raises(CacheWaitTimeout):
        cache.get_or_generate(request)
    release.set()
    leader.join(5)
    assert cache.in_flight == 0


def clue_scene(red, blue, table, relation):
    objects = {
        red: {"key": red, "source": "cup", "translation": "taza",
              "anchorPoint": {"x": 0.2, "y": 0.3}},
        blue: {"key": blue, "source": "cup", "translation": "taza",
               "anchorPoint": {"x": 0.8, "y": 0.3}},
        table: {"key": table, "source": "table", "translation": "mesa",
                "anchorPoint": {"x": 0.5, "y": 0.7}},
    }
    return objects, {
        "targetLanguage": "es",
        "sceneTitle": "Desk",
        "sceneSummary": "Two cups on a table.",
        "attributes": [
            {"key": f"{red}:color", "objectKey": red, "source": "red", "translation": "roja"},
            {"key": f"{blue}:color", "objectKey": blue, "source": "blue", "translation": "azul"},
        ],
        "relationships": [{
            "key": relation, "source": "on", "translation": "sobre",
            "subjectObjectKey": red, "referenceObjectKey": table,
        }],
    }


def test_duplicate_objects_keep_identity_and_relations_after_remapping():
    first = ids(4)
    objects, payload = clue_scene(*first)
    output = json.dumps({"clues": [
        {"clue": "es roja", "answerObjectKey": first[0], "objectKeys": [first[0]],
         "relationshipKeys": [first[3]]},
        {"clue": "es azul", "answerObjectKey": first[1], "objectKeys": [first[1]],
         "relationshipKeys": []},
    ]})
    client = FakeClient([output])
    service = ISpyClueService(
        client, config(), tracer=NoOpAITracer(), provider="openai", cache=ResultCache()
    )
    service.generate({**payload, "objects": list(objects.values())}, cache_scope=PUBLIC)

    red, blue, table, relation = ids(4)
    objects, payload = clue_scene(red, blue, table, relation)
    reordered = {
        **payload,
        "objects": [objects[table], objects[blue], objects[red]],
        "attributes": payload["attributes"][::-1],
    }
    result = service.generate(reordered, cache_scope=PUBLIC)

    assert client.calls == 1
    by_clue = {clue.clue: clue for clue in result.clues}
    assert by_clue["es roja"].answer_object_key == red
    assert by_clue["es roja"].relationship_keys == [relation]
    assert by_clue["es azul"].answer_object_key == blue


def test_reference_map_aliases_by_content_not_by_id():
    first = ReferenceMap(scene("a", "b", "r"))
    second = ReferenceMap(scene("x", "y", "s"))
    assert first.canonical_payload(scene("a", "b", "r")) == second.canonical_payload(
        scene("x", "y", "s")
    )
    assert first.to_aliases({"key": "a:color"}) == {"key": "o1:color"}
    assert second.from_aliases({"objectKeys": ["o1", "o2"]}) == {"objectKeys": ["x", "y"]}
    assert first.to_aliases({"key": "unknown"}) is None


def direct_request(
    calls,
    *,
    version=VERSION,
    scope=PUBLIC,
    payload=None,
    approved=("a",),
    served="a",
    result=None,
    compute=None,
    wait_seconds=None,
):
    payload = payload or {"objects": [{"key": "x", "source": "cup"}]}

    def generate():
        calls.append(1)
        return Generated(result or {"key": "x"}, served, "model")

    return CacheRequest(
        version=version,
        scope=scope,
        payload=payload,
        generation=[{"model": "model"}],
        approved_deployments=frozenset(approved),
        compute=compute or generate,
        encode=lambda value: value,
        decode=lambda value: value,
        wait_seconds=wait_seconds,
    )


def curated_session():
    session_id = uuid4()
    content = {"items": [
        {"id": "cup", "translation": "cup", "attributes": {"color": "red"}},
        {"id": "table", "translation": "table"},
    ]}
    cup = SceneObject(
        id=uuid5(session_id, "curated:cup"), session_id=session_id, label="cup",
        attributes={"color": "red"},
    )
    table = SceneObject(
        id=uuid5(session_id, "curated:table"), session_id=session_id, label="table"
    )
    relation = SceneObjectRelation(
        subject_scene_object_id=cup.id, relation="on",
        reference_scene_object_id=table.id, source_relation_key="precomputed-v1",
    )
    return session_id, content, [cup, table], [relation]


def test_only_unchanged_curated_content_is_public():
    session_id, content, objects, relations = curated_session()
    assert is_curated_content(session_id, content, objects, relations)
    assert is_curated_content(session_id, content, objects[:1], [])

    added = SceneObject(id=uuid4(), session_id=session_id, label="my diary")
    assert not is_curated_content(session_id, content, [*objects, added], relations)
    edited = objects[0].model_copy(update={"attributes": {"color": "blue"}})
    assert not is_curated_content(session_id, content, [edited, objects[1]], relations)
    renamed = objects[1].model_copy(update={"label": "desk"})
    assert not is_curated_content(session_id, content, [objects[0], renamed], relations)
    changed = relations[0].model_copy(update={"source_relation_key": None})
    assert not is_curated_content(session_id, content, objects, [changed])
    assert not is_curated_content(uuid4(), content, objects, relations)


def test_cache_settings_are_read_from_the_environment():
    settings = load_ai_settings({})
    assert settings.result_cache.enabled is True
    assert settings.result_cache.ttl_seconds == 86_400
    assert settings.result_cache.max_entries == 2_000
    custom = load_ai_settings({
        "AI_RESULT_CACHE_ENABLED": "false",
        "AI_RESULT_CACHE_TTL_SECONDS": "60",
        "AI_RESULT_CACHE_MAX_ENTRIES": "5",
    })
    assert custom.result_cache.model_dump() == {
        "enabled": False, "ttl_seconds": 60, "max_entries": 5
    }
    with pytest.raises(AiConfigurationError):
        load_ai_settings({"AI_RESULT_CACHE_MAX_ENTRIES": "0"})


def test_learning_task_hit_round_trips_and_revalidates():
    from test_learning_task_service import INPUT, response_body, tasks

    from app.ai.features.learning_tasks import LearningTaskResult, LearningTaskService

    client = FakeClient([response_body(LearningTaskResult.model_validate(tasks()))])
    service = LearningTaskService(
        client, config(), tracer=NoOpAITracer(), provider="openai", cache=ResultCache()
    )
    first = service.generate(INPUT, cache_scope=PUBLIC)
    second = service.generate(INPUT, cache_scope=PUBLIC)
    assert client.calls == 1
    assert second == first
