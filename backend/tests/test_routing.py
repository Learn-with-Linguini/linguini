"""Routed clients: deployment priority, credential rotation, shared budget."""

import json
import time
from contextlib import contextmanager

import httpx
import pytest
from test_scene_translation_service import PAYLOAD, VALID_OUTPUT

from app.ai import registry
from app.ai.adapters import gemini
from app.ai.adapters.openai import OpenAITextClient
from app.ai.adapters.openrouter import OpenRouterTextClient
from app.ai.config import AiConfigurationError, parse_ai_config
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.metadata import ResponseMetadata, TokenUsage
from app.ai.contracts.text import TextModelConfig, TextModelRequest, TextModelResponse
from app.ai.features.translation.service import SceneTranslationError, SceneTranslationService
from app.ai.pool import CredentialPool, ProviderPool
from app.ai.routing import InvocationContext, RoutedModelClient, RouteTarget
from app.ai.settings import AiFeature, load_ai_settings

Code = ProviderErrorCode
Scope = ProviderFailureScope
REQUEST = TextModelRequest(
    system_prompt="s", user_content="u", json_schema_name="n", json_schema={}, prompt_version="v"
)


def error(code, scope, status=None):
    return ProviderError(code, "failed", status_code=status, scope=scope)


TIMEOUT = error(Code.PROVIDER_TIMEOUT, Scope.SERVICE)
RATE_LIMITED = error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 429)
AUTH = error(Code.PROVIDER_AUTH, Scope.CREDENTIALS, 401)
REFUSED = error(Code.PROVIDER_REFUSED, Scope.RESPONSE)
BAD_SCHEMA = error(Code.PROVIDER_ERROR, Scope.REQUEST, 400)
INVALID_OUTPUT = error(Code.PROVIDER_RESPONSE_INVALID, Scope.RESPONSE)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeProvider:
    """Plays scripted outcomes; every ``generate`` is one outbound call."""

    def __init__(self, outcomes=None, clock=None, advance=0.0):
        self.outcomes = list(outcomes or [])
        self.calls = []
        self.clock = clock
        self.advance = advance

    def generate(self, request, *, timeout_seconds=None):
        self.calls.append(timeout_seconds)
        if self.clock:
            self.clock.now += self.advance
        outcome = self.outcomes.pop(0) if self.outcomes else "{}"
        if isinstance(outcome, ProviderError):
            raise outcome
        return TextModelResponse(
            output_text=outcome,
            model_name="requested",
            prompt_version=request.prompt_version,
            input_tokens=3,
            output_tokens=4,
            metadata=ResponseMetadata(
                provider="fake",
                endpoint="fake",
                requested_model="requested",
                model="served",
                usage=TokenUsage(input_tokens=3, output_tokens=4, total_tokens=7),
            ),
        )


def ai_config(deployments: dict[str, list[str]]):
    credentials = {cid for ids in deployments.values() for cid in ids}
    return parse_ai_config(
        {
            "credentials": {
                cid: {
                    "adapter": "openrouter",
                    "env": [f"KEY_{cid.upper()}"],
                    "quota_group": cid,
                    "billing_group": "billing",
                }
                for cid in credentials
            },
            "deployments": {
                did: {
                    "adapter": "openrouter",
                    "api": "responses",
                    "model": f"model-{did}",
                    "capabilities": ["text", "jsonSchema"],
                    "credentials": ids,
                    "defaults": {"timeout_seconds": 60},
                    "upstream_fallback": {"allow_fallbacks": True},
                }
                for did, ids in deployments.items()
            },
            "routes": {feature.value: {"enabled": False} for feature in AiFeature},
        }
    )


class Route:
    """A routed client over fake providers, one per (deployment, credential)."""

    def __init__(self, deployments, outcomes=None, max_calls=4, deadline=None, clock=None, **kw):
        self.clock = clock or Clock()
        self.credentials = CredentialPool(
            ai_config(deployments),
            {cid: f"sk-{cid}" for ids in deployments.values() for cid in ids},
            clock=self.clock,
        )
        self.providers = {
            (did, cid): FakeProvider((outcomes or {}).get((did, cid)), self.clock, **kw)
            for did, ids in deployments.items()
            for cid in ids
        }
        self.order = []

        def target(did):
            def build(secret):
                provider = self.providers[(did, secret.removeprefix("sk-"))]
                original = provider.generate

                def generate(request, **options):
                    self.order.append((did, secret.removeprefix("sk-")))
                    return original(request, **options)

                provider.generate = generate
                return provider

            return RouteTarget(
                did,
                "openrouter",
                TextModelConfig(model_name=f"model-{did}", timeout_seconds=60),
                build,
            )

        self.tracer = RecordingTracer()
        self.client = RoutedModelClient(
            "text",
            tuple(target(did) for did in deployments),
            self.credentials,
            max_model_calls=max_calls,
            deadline_seconds=deadline,
            clients=ProviderPool(self.credentials).clients,
            tracer=self.tracer,
            clock=self.clock,
        )


class _Observation:
    def __init__(self, record):
        self.record = record

    def update(self, **fields):
        self.record.setdefault("updates", []).append(fields)

    def record_content(self, **_):
        pass


class RecordingTracer:
    def __init__(self):
        self.records = []

    @contextmanager
    def _observe(self, kind, name, **fields):
        record = {"kind": kind, "name": name, **fields}
        self.records.append(record)
        yield _Observation(record)

    def trace(self, name, **fields):
        return self._observe("trace", name, **fields)

    def span(self, name, **fields):
        return self._observe("span", name, **fields)

    def generation(self, name, **fields):
        return self._observe("generation", name, **fields)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    def forbidden(_seconds):
        raise AssertionError("routing must never sleep")

    monkeypatch.setattr(time, "sleep", forbidden)


def test_priority_uses_the_first_deployment_and_rotates_its_credentials():
    route = Route({"primary": ["a", "b"], "backup": ["c"]})
    for _ in range(4):
        response = route.client.generate(REQUEST)
        assert response.route.deployment_id == "primary"
        assert response.route.attempts == 1
        assert response.route.fallback_reason is None
    assert route.order == [("primary", "a"), ("primary", "b")] * 2


def test_service_failure_fails_over_to_the_next_deployment():
    route = Route({"primary": ["a"], "backup": ["c"]}, {("primary", "a"): [TIMEOUT]})
    response = route.client.generate(REQUEST)
    assert route.order == [("primary", "a"), ("backup", "c")]
    assert (response.route.deployment_id, response.route.credential_id) == ("backup", "c")
    assert response.route.attempts == 2
    assert response.route.fallback_reason == "providerTimeout"
    assert response.route.model == "served"


def test_rate_limit_moves_to_the_next_credential_first():
    route = Route({"primary": ["a", "b"], "backup": ["c"]}, {("primary", "a"): [RATE_LIMITED]})
    response = route.client.generate(REQUEST)
    assert route.order == [("primary", "a"), ("primary", "b")]
    assert response.route.fallback_reason == "providerRateLimited"


def test_authentication_failure_disables_the_key_and_tries_the_next():
    route = Route({"primary": ["a", "b"]}, {("primary", "a"): [AUTH]})
    assert route.client.generate(REQUEST).route.credential_id == "b"
    assert route.client.generate(REQUEST).route.credential_id == "b"
    assert route.order == [("primary", "a"), ("primary", "b"), ("primary", "b")]


def test_authentication_failure_with_one_key_moves_to_the_next_deployment():
    route = Route({"primary": ["a"], "backup": ["c"]}, {("primary", "a"): [AUTH]})
    assert route.client.generate(REQUEST).route.deployment_id == "backup"


@pytest.mark.parametrize("terminal", [REFUSED, BAD_SCHEMA, INVALID_OUTPUT])
def test_refusals_request_errors_and_invalid_output_are_not_failed_over(terminal):
    route = Route({"primary": ["a", "b"], "backup": ["c"]}, {("primary", "a"): [terminal]})
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST)
    assert raised.value is terminal
    assert route.order == [("primary", "a")]


def test_budget_bounds_failover_and_reraises_the_last_failure():
    outcomes = {key: [TIMEOUT] for key in [("primary", "a"), ("primary", "b"), ("backup", "c")]}
    route = Route({"primary": ["a", "b"], "backup": ["c"]}, outcomes, max_calls=2)
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST)
    assert raised.value.code is Code.PROVIDER_TIMEOUT
    assert len(route.order) == 2


def test_every_deployment_unavailable_fails_without_a_call():
    route = Route({"primary": ["a"], "backup": ["c"]})
    for cid, did in (("a", "primary"), ("c", "backup")):
        lease = route.credentials.acquire(did)
        route.credentials.report_failure(lease, AUTH)
        assert lease.credential_id == cid
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST)
    assert raised.value.code is Code.PROVIDER_AUTH
    assert route.order == []


def test_no_call_starts_after_the_deadline():
    clock = Clock()
    route = Route(
        {"primary": ["a"], "backup": ["c"]},
        {("primary", "a"): [TIMEOUT]},
        deadline=30,
        clock=clock,
        advance=31,
    )
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST)
    assert raised.value is TIMEOUT
    assert route.order == [("primary", "a")]


def test_call_timeout_is_capped_at_the_time_left():
    clock = Clock()
    route = Route({"primary": ["a"]}, deadline=90, clock=clock)
    invocation = route.client.start_invocation()
    clock.now += 50
    route.client.generate(REQUEST, invocation)
    assert route.providers[("primary", "a")].calls == [pytest.approx(40)]
    route.client.generate(REQUEST)
    assert route.providers[("primary", "a")].calls[-1] is None


def test_expired_invocation_makes_no_call():
    clock = Clock()
    route = Route({"primary": ["a"]}, deadline=10, clock=clock)
    invocation = route.client.start_invocation()
    clock.now += 11
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST, invocation)
    assert raised.value.code is Code.PROVIDER_TIMEOUT
    assert route.order == []


def test_invocation_budget_is_shared_across_calls():
    invocation = InvocationContext(2)
    route = Route({"primary": ["a"]})
    route.client.generate(REQUEST, invocation)
    route.client.generate(REQUEST, invocation)
    assert not invocation.can_call()
    with pytest.raises(ProviderError):
        route.client.generate(REQUEST, invocation)
    assert len(route.order) == 2


def translator(route):
    config = TextModelConfig(model_name="model-primary", max_retries=1)
    return SceneTranslationService(route.client, config, tracer=route.tracer, provider="openrouter")


def test_feature_repair_shares_the_route_budget():
    route = Route(
        {"primary": ["a"], "backup": ["c"]},
        {("primary", "a"): [TIMEOUT], ("backup", "c"): ["not json"]},
        max_calls=2,
    )
    with pytest.raises(SceneTranslationError):
        translator(route).translate(PAYLOAD)
    assert route.order == [("primary", "a"), ("backup", "c")]


def test_feature_repair_runs_when_budget_remains():
    route = Route(
        {"primary": ["a"], "backup": ["c"]},
        {("primary", "a"): [TIMEOUT, VALID_OUTPUT], ("backup", "c"): ["not json"]},
        max_calls=3,
    )
    result = translator(route).translate(PAYLOAD)
    assert result.objects[0].translation == "silla"
    assert route.order == [("primary", "a"), ("backup", "c"), ("primary", "a")]


def test_feature_repair_stays_bounded_by_max_retries():
    route = Route({"primary": ["a"]}, {("primary", "a"): ["bad", "bad", "bad"]}, max_calls=5)
    with pytest.raises(SceneTranslationError):
        translator(route).translate(PAYLOAD)
    assert len(route.order) == 2


def test_tracing_records_attempts_route_and_usage_without_secrets():
    route = Route(
        {"primary": ["a"], "backup": ["c"]},
        {("primary", "a"): [TIMEOUT], ("backup", "c"): [VALID_OUTPUT]},
    )
    translator(route).translate(PAYLOAD)

    calls = [r for r in route.tracer.records if r["name"] == "model-call"]
    assert [c["metadata"]["deployment"] for c in calls] == ["primary", "backup"]
    assert calls[0]["updates"][0]["error_code"] == "providerTimeout"
    assert calls[0]["updates"][0]["metadata"]["outcome"] == "failover"
    assert calls[1]["metadata"]["fallbackReason"] == "providerTimeout"
    assert calls[1]["updates"][0]["total_tokens"] == 7

    generation = next(r for r in route.tracer.records if r["kind"] == "generation")
    final = generation["updates"][-1]
    assert final["metadata"] == {
        "deployment": "backup",
        "credentialId": "c",
        "servedModel": "served",
        "routeAttempts": 2,
        "fallbackReason": "providerTimeout",
    }
    assert final["total_tokens"] == 7
    assert "sk-" not in repr(route.tracer.records)


@pytest.mark.parametrize("max_retries", [0, 1])
def test_directly_injected_clients_keep_the_feature_call_count(max_retries):
    provider = FakeProvider([TIMEOUT, TIMEOUT, VALID_OUTPUT])
    config = TextModelConfig(model_name="m", max_retries=max_retries)
    service = SceneTranslationService(
        provider, config, tracer=RecordingTracer(), provider="openrouter"
    )
    with pytest.raises(SceneTranslationError):
        service.translate(PAYLOAD)
    assert len(provider.calls) == 1 + max_retries


def priority_settings(tmp_path, policy="priority"):
    path = tmp_path / "ai.toml"
    lines = []
    for cid in ("a", "c"):
        lines += [
            f"[credentials.{cid}]",
            'adapter = "openrouter"',
            f'env = ["KEY_{cid.upper()}"]',
            f'quota_group = "{cid}"',
            'billing_group = "billing"',
        ]
    for did, cid in (("primary", "a"), ("backup", "c")):
        lines += [
            f"[deployments.{did}]",
            'adapter = "openrouter"',
            'api = "responses"',
            f'model = "model-{did}"',
            'capabilities = ["text", "jsonSchema"]',
            f'credentials = ["{cid}"]',
            "defaults = { timeout_seconds = 60, max_retries = 1 }",
            "upstream_fallback = { allow_fallbacks = true, models = ['vendor/other'] }",
        ]
    lines += [
        "[routes.sceneTranslation]",
        'deployments = ["primary", "backup"]',
        f'policy = "{policy}"',
        "deadline_seconds = 120",
        "max_model_calls = 3",
    ]
    for feature in ("sceneAnalysis", "learningTask", "ispyClue", "ispyGuess"):
        lines += [f"[routes.{feature}]", "enabled = false"]
    path.write_text("\n".join(lines))
    return load_ai_settings({"AI_CONFIG_FILE": str(path), "KEY_A": "sk-a", "KEY_C": "sk-c"})


def test_registry_builds_priority_routes_from_config(tmp_path, monkeypatch):
    built = {}

    def fake(key, config, **options):
        provider = FakeProvider([TIMEOUT] if key == "sk-a" else [VALID_OUTPUT])
        built[key] = (config.model_name, options, provider)
        return provider

    monkeypatch.setattr(registry, "OpenRouterTextClient", fake)
    translator = registry.build_scene_translator(priority_settings(tmp_path), RecordingTracer())
    assert translator.translate(PAYLOAD).objects[0].translation == "silla"
    assert built["sk-a"][0] == "model-primary"
    assert built["sk-c"][0] == "model-backup"
    assert built["sk-c"][1] == {"allow_fallbacks": True, "fallback_models": ("vendor/other",)}


def test_primary_policy_uses_only_the_first_deployment(tmp_path, monkeypatch):
    models = []

    def fake(key, config, **_):
        models.append(config.model_name)
        return FakeProvider([TIMEOUT] * 3)

    monkeypatch.setattr(registry, "OpenRouterTextClient", fake)
    settings = priority_settings(tmp_path, policy="primary")
    client, _ = registry.build_routed_client("text", settings, AiFeature.SCENE_TRANSLATION)
    with pytest.raises(ProviderError):
        client.generate(REQUEST)
    assert models == ["model-primary"]


def deployment(**extra):
    data = {
        "credentials": {
            "or": {"adapter": "openrouter", "env": ["K"], "quota_group": "q", "billing_group": "b"},
            "gm": {"adapter": "gemini", "env": ["G"], "quota_group": "g", "billing_group": "b"},
        },
        "deployments": {"d": extra},
        "routes": {feature.value: {"enabled": False} for feature in AiFeature},
    }
    return data


def test_openrouter_deployments_must_state_upstream_fallback():
    base = {
        "adapter": "openrouter",
        "api": "responses",
        "model": "m",
        "capabilities": ["text"],
        "credentials": ["or"],
        "defaults": {"timeout_seconds": 30},
    }
    with pytest.raises(AiConfigurationError, match="upstream_fallback"):
        parse_ai_config(deployment(**base))
    gemini_base = {**base, "adapter": "gemini", "api": "generateContent", "credentials": ["gm"]}
    with pytest.raises(AiConfigurationError, match="only supported for openrouter"):
        parse_ai_config(deployment(**gemini_base, upstream_fallback={"allow_fallbacks": True}))


def responses_client(cls, handler, **options):
    return cls(
        "sk-test",
        TextModelConfig(model_name="m", timeout_seconds=60),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **options,
    )


def ok_body():
    return {
        "id": "resp_1",
        "model": "m",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
    }


def test_openrouter_sends_upstream_fallback_explicitly():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    responses_client(OpenRouterTextClient, handler).generate(REQUEST)
    responses_client(
        OpenRouterTextClient, handler, allow_fallbacks=False, fallback_models=("vendor/x",)
    ).generate(REQUEST)
    responses_client(OpenAITextClient, handler).generate(REQUEST)

    assert bodies[0]["provider"] == {"allow_fallbacks": True}
    assert "models" not in bodies[0]
    assert bodies[1]["provider"] == {"allow_fallbacks": False}
    assert bodies[1]["models"] == ["vendor/x"]
    assert "provider" not in bodies[2]


def test_responses_transport_uses_the_capped_timeout_for_one_call():
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json=ok_body())

    client = responses_client(OpenAITextClient, handler)
    client.generate(REQUEST, timeout_seconds=12.5)
    client.generate(REQUEST)
    assert 12 < timeouts[0] <= 12.5
    assert 59 < timeouts[1] <= 60


def test_gemini_sdk_retries_are_pinned_to_one_attempt(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(gemini.genai, "Client", fake_client)
    client = gemini.GeminiTextClient(
        "key", TextModelConfig(model_name="gemini-x", timeout_seconds=30)
    )
    client._new_client()
    options = captured["http_options"]
    assert options.retry_options.attempts == 1
    assert options.timeout == 30_000


def test_eval_judge_disables_sdk_retries():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "evals" / "judge.py").read_text()
    assert "max_retries=0" in source
    assert "max_retries=2" not in source


@pytest.mark.parametrize("max_calls, expected_calls", [(1, 1), (2, 2), (5, 2)])
def test_normalized_invalid_output_repair_uses_invocation_budget(max_calls, expected_calls):
    invalid = error(Code.PROVIDER_RESPONSE_INVALID, Scope.RESPONSE)
    route = Route(
        {"primary": ["a"]}, {("primary", "a"): [invalid, invalid, invalid]}, max_calls=max_calls
    )
    with pytest.raises(SceneTranslationError):
        translator(route).translate(PAYLOAD)
    assert len(route.order) == expected_calls


def test_normalized_invalid_output_is_repaired_when_budget_remains():
    invalid = error(Code.PROVIDER_RESPONSE_INVALID, Scope.RESPONSE)
    route = Route({"primary": ["a"]}, {("primary", "a"): [invalid, VALID_OUTPUT]}, max_calls=2)
    assert translator(route).translate(PAYLOAD).objects[0].translation == "silla"
    assert len(route.order) == 2
