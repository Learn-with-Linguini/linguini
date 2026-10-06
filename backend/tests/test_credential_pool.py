"""Credential pool: round robin, cooldowns, disabling and client reuse."""

import threading
from collections import Counter

import pytest

from app.ai import registry
from app.ai.config import parse_ai_config
from app.ai.contracts.errors import ProviderError, ProviderErrorCode, ProviderFailureScope
from app.ai.contracts.text import TextModelConfig, TextModelRequest, TextModelResponse
from app.ai.observability import NoOpAITracer
from app.ai.pool import (
    CredentialPool,
    Health,
    HealthReason,
    HealthScope,
    InMemoryPoolState,
    ProviderPool,
)
from app.ai.routing import RoutedModelClient, RouteTarget
from app.ai.runtime import AiRuntime
from app.ai.settings import AiFeature, load_ai_settings

Code = ProviderErrorCode
Scope = ProviderFailureScope
DEPLOYMENT = "chat"
REQUEST = TextModelRequest(
    system_prompt="s", user_content="u", json_schema_name="n", json_schema={}, prompt_version="v"
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def ai_config(groups: dict[str, str]):
    """One openrouter deployment whose credentials map to ``groups``."""
    routes = {feature.value: {"enabled": False} for feature in AiFeature}
    return parse_ai_config(
        {
            "credentials": {
                cid: {
                    "adapter": "openrouter",
                    "env": [f"KEY_{cid.upper()}"],
                    "quota_group": group,
                    "billing_group": "billing",
                }
                for cid, group in groups.items()
            },
            "deployments": {
                DEPLOYMENT: {
                    "adapter": "openrouter",
                    "api": "responses",
                    "model": "openai/gpt-4o-mini",
                    "capabilities": ["text", "jsonSchema"],
                    "credentials": list(groups),
                    "defaults": {"timeout_seconds": 60},
                    "upstream_fallback": {"allow_fallbacks": True},
                }
            },
            "routes": routes,
        }
    )


def pool(groups=None, secrets=None, clock=None, **options) -> CredentialPool:
    groups = groups or {"a": "g1", "b": "g2", "c": "g3"}
    secrets = {cid: f"sk-{cid}" for cid in groups} if secrets is None else secrets
    return CredentialPool(ai_config(groups), secrets, clock=clock or Clock(), **options)


def error(code, scope, retry_after=None, status=None):
    return ProviderError(
        code, "failed", status_code=status, retry_after_seconds=retry_after, scope=scope
    )


def picks(credentials: CredentialPool, count: int) -> list[str]:
    return [credentials.acquire(DEPLOYMENT).credential_id for _ in range(count)]


def test_round_robin_cycles_through_credentials():
    assert picks(pool(), 6) == ["a", "b", "c", "a", "b", "c"]


def test_concurrent_selection_is_balanced():
    credentials = pool()
    barrier = threading.Barrier(30)
    chosen: list[str] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        lease = credentials.acquire(DEPLOYMENT)
        with lock:
            chosen.append(lease.credential_id)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert Counter(chosen) == {"a": 10, "b": 10, "c": 10}


def test_credentials_without_a_secret_are_skipped():
    assert picks(pool(secrets={"a": "sk-a", "c": "sk-c"}), 4) == ["a", "c", "a", "c"]


def test_rate_limit_cools_down_the_quota_group_until_retry_after():
    clock = Clock()
    credentials = pool({"a": "shared", "b": "shared", "c": "solo"}, clock=clock)
    lease = credentials.acquire(DEPLOYMENT)
    credentials.report_failure(lease, error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 5))

    assert picks(credentials, 3) == ["c", "c", "c"]
    health = credentials.health(HealthScope.QUOTA_GROUP, "shared")
    assert health.reason is HealthReason.RATE_LIMITED and not health.disabled

    clock.now += 5
    assert set(picks(credentials, 3)) == {"a", "b", "c"}


def test_rate_limit_without_retry_after_uses_the_short_default():
    clock = Clock()
    credentials = pool({"a": "g"}, clock=clock, rate_limit_cooldown_seconds=10)
    credentials.report_failure(
        credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA)
    )

    clock.now += 9
    with pytest.raises(ProviderError) as raised:
        credentials.acquire(DEPLOYMENT)
    assert raised.value.code is Code.PROVIDER_RATE_LIMITED
    assert raised.value.retry_after_seconds == pytest.approx(1)
    clock.now += 1
    assert picks(credentials, 1) == ["a"]


def test_exhausted_credits_cool_down_longer_than_a_rate_limit():
    clock = Clock()
    credentials = pool(
        {"a": "g"},
        clock=clock,
        rate_limit_cooldown_seconds=10,
        quota_exhausted_cooldown_seconds=300,
    )
    credentials.report_failure(
        credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_ERROR, Scope.QUOTA, status=402)
    )

    health = credentials.health(HealthScope.QUOTA_GROUP, "g")
    assert health.reason is HealthReason.QUOTA_EXHAUSTED
    assert health.cooldown_until == clock.now + 300
    assert not health.disabled


def test_shorter_retry_after_never_shortens_an_existing_cooldown():
    clock = Clock()
    credentials = pool({"a": "g", "b": "g"}, clock=clock)
    first, second = credentials.acquire(DEPLOYMENT), credentials.acquire(DEPLOYMENT)
    credentials.report_failure(first, error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 30))
    credentials.report_failure(second, error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 2))

    assert credentials.health(HealthScope.QUOTA_GROUP, "g").cooldown_until == clock.now + 30


def test_authentication_failure_disables_only_that_credential():
    clock = Clock()
    credentials = pool({"a": "shared", "b": "shared"}, clock=clock)
    lease = credentials.acquire(DEPLOYMENT)
    credentials.report_failure(lease, error(Code.PROVIDER_AUTH, Scope.CREDENTIALS, status=401))

    clock.now += 10_000
    assert picks(credentials, 3) == ["b", "b", "b"]
    assert credentials.health(HealthScope.CREDENTIAL, "a").disabled
    assert credentials.health(HealthScope.QUOTA_GROUP, "shared") == Health()


@pytest.mark.parametrize(
    "failure",
    [
        error(Code.PROVIDER_ERROR, Scope.REQUEST, status=403),
        error(Code.PROVIDER_RESPONSE_INVALID, Scope.RESPONSE),
        error(Code.PROVIDER_REFUSED, Scope.RESPONSE),
    ],
)
def test_request_and_response_failures_change_no_health(failure):
    credentials = pool({"a": "g"})
    credentials.report_failure(credentials.acquire(DEPLOYMENT), failure)
    assert picks(credentials, 2) == ["a", "a"]
    assert credentials.health(HealthScope.CREDENTIAL, "a") == Health()
    assert credentials.health(HealthScope.DEPLOYMENT, DEPLOYMENT) == Health()


def test_every_credential_disabled_fails_without_a_call():
    credentials = pool({"a": "g1", "b": "g2"})
    for _ in range(2):
        credentials.report_failure(
            credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_AUTH, Scope.CREDENTIALS)
        )
    with pytest.raises(ProviderError) as raised:
        credentials.acquire(DEPLOYMENT)
    assert raised.value.code is Code.PROVIDER_AUTH
    assert raised.value.scope is Scope.CREDENTIALS
    assert "sk-" not in str(raised.value)


def test_every_credential_cooling_reports_the_soonest_retry():
    clock = Clock()
    credentials = pool({"a": "g1", "b": "g2"}, clock=clock)
    credentials.report_failure(
        credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 20)
    )
    credentials.report_failure(
        credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 7)
    )
    with pytest.raises(ProviderError) as raised:
        credentials.acquire(DEPLOYMENT)
    assert raised.value.code is Code.PROVIDER_RATE_LIMITED
    assert raised.value.retry_after_seconds == pytest.approx(7)
    assert raised.value.transient


def test_service_retry_after_cools_down_the_deployment_not_credentials():
    clock = Clock()
    credentials = pool({"a": "g"}, clock=clock)
    lease = credentials.acquire(DEPLOYMENT)
    credentials.report_failure(lease, error(Code.PROVIDER_UNAVAILABLE, Scope.SERVICE, 3, 503))

    with pytest.raises(ProviderError) as raised:
        credentials.acquire(DEPLOYMENT)
    assert raised.value.code is Code.PROVIDER_UNAVAILABLE
    assert credentials.health(HealthScope.CREDENTIAL, "a") == Health()
    assert credentials.health(HealthScope.QUOTA_GROUP, "g") == Health()

    clock.now += 3
    credentials.report_success(credentials.acquire(DEPLOYMENT))
    assert credentials.health(HealthScope.DEPLOYMENT, DEPLOYMENT) == Health()


def test_service_failures_without_retry_after_are_tracked_but_never_block():
    credentials = pool({"a": "g"})
    for _ in range(3):
        credentials.report_failure(
            credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_TIMEOUT, Scope.SERVICE)
        )
    assert credentials.health(HealthScope.DEPLOYMENT, DEPLOYMENT).consecutive_failures == 3
    credentials.report_success(credentials.acquire(DEPLOYMENT))
    assert credentials.health(HealthScope.DEPLOYMENT, DEPLOYMENT) == Health()


def test_unknown_model_cools_down_the_deployment():
    clock = Clock()
    credentials = pool({"a": "g"}, clock=clock, deployment_cooldown_seconds=30)
    credentials.report_failure(
        credentials.acquire(DEPLOYMENT), error(Code.PROVIDER_ERROR, Scope.MODEL, status=404)
    )
    with pytest.raises(ProviderError) as raised:
        credentials.acquire(DEPLOYMENT)
    assert raised.value.scope is Scope.MODEL
    clock.now += 30
    assert picks(credentials, 1) == ["a"]


def test_state_is_injectable():
    state = InMemoryPoolState()
    first = pool({"a": "g", "b": "g"}, state=state)
    first.report_failure(
        first.acquire(DEPLOYMENT), error(Code.PROVIDER_AUTH, Scope.CREDENTIALS)
    )
    second = pool({"a": "g", "b": "g"}, state=state)
    assert picks(second, 2) == ["b", "b"]


def test_lease_and_pool_repr_hide_secrets():
    credentials = pool({"a": "g"})
    lease = credentials.acquire(DEPLOYMENT)
    assert lease.secret == "sk-a"
    assert "sk-a" not in repr(lease)
    assert "sk-a" not in repr(credentials)


class FakeClient:
    def __init__(self, key, config, failures=None, gate=None, entered=None):
        self.key = key
        self.config = config
        self.failures = failures or {}
        self.gate = gate
        self.entered = entered

    def generate(self, request):
        if self.entered:
            self.entered.set()
        if self.gate:
            self.gate.wait()
        if failure := self.failures.get(self.key):
            raise failure
        return TextModelResponse(output_text="{}", model_name="m", prompt_version="v")


def pooled(credentials, factory, config=None):
    """A one-deployment route with a one-call budget, so failures surface."""
    return RoutedModelClient(
        "text",
        (
            RouteTarget(
                DEPLOYMENT, "openrouter", config or TextModelConfig(model_name="m"), factory
            ),
        ),
        credentials,
        max_model_calls=1,
        clients=ProviderPool(credentials).clients,
    )


def test_clients_are_reused_per_deployment_and_credential():
    built = []

    def factory(secret):
        client = FakeClient(secret, None)
        built.append(client)
        return client

    client = pooled(pool({"a": "g1", "b": "g2"}), factory)
    for _ in range(6):
        client.generate(REQUEST)

    assert sorted(c.key for c in built) == ["sk-a", "sk-b"]
    assert all(c.key in ("sk-a", "sk-b") for c in built)


def test_failure_rotates_to_another_quota_group_and_reraises():
    failures = {"sk-a": error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 60, 429)}
    calls = []

    def factory(secret):
        calls.append(secret)
        return FakeClient(secret, None, failures)

    client = pooled(pool({"a": "g1", "b": "g2"}), factory)
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST)
    assert raised.value is failures["sk-a"]
    assert client.generate(REQUEST).output_text == "{}"
    assert client.generate(REQUEST).output_text == "{}"
    assert calls == ["sk-a", "sk-b"]


def test_keys_sharing_a_quota_group_cool_down_together():
    failures = {"sk-a": error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 60, 429)}
    calls = []

    def factory(secret):
        calls.append(secret)
        return FakeClient(secret, None, failures)

    client = pooled(pool({"a": "shared", "b": "shared"}), factory)
    with pytest.raises(ProviderError):
        client.generate(REQUEST)
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST)
    assert raised.value.code is Code.PROVIDER_RATE_LIMITED
    assert calls == ["sk-a"]


def test_lock_is_not_held_during_the_model_call():
    gate, entered = threading.Event(), threading.Event()
    credentials = pool({"a": "g1", "b": "g2"})
    client = pooled(
        credentials, lambda secret: FakeClient(secret, None, gate=gate, entered=entered)
    )
    slow = threading.Thread(target=client.generate, args=(REQUEST,))
    slow.start()
    try:
        assert entered.wait(timeout=2)
        selected = []
        other = threading.Thread(
            target=lambda: selected.append(credentials.acquire(DEPLOYMENT).credential_id)
        )
        other.start()
        other.join(timeout=2)
        assert selected == ["b"]
    finally:
        gate.set()
        slow.join()


def two_key_settings(tmp_path, groups):
    lines = []
    for cid, group in groups.items():
        lines += [
            f"[credentials.{cid}]",
            'adapter = "openrouter"',
            f'env = ["KEY_{cid.upper()}"]',
            f'quota_group = "{group}"',
            'billing_group = "billing"',
        ]
    lines += [
        "[deployments.shared]",
        'adapter = "openrouter"',
        'api = "responses"',
        'model = "openai/gpt-4o-mini"',
        'capabilities = ["text", "jsonSchema"]',
        f"credentials = {list(groups)!r}".replace("'", '"'),
        "defaults = { timeout_seconds = 60, max_retries = 1 }",
        "upstream_fallback = { allow_fallbacks = true }",
    ]
    for feature in ("sceneTranslation", "ispyClue"):
        lines += [
            f"[routes.{feature}]",
            'deployments = ["shared"]',
            "deadline_seconds = 120",
            "max_model_calls = 2",
        ]
    for feature in ("sceneAnalysis", "learningTask", "ispyGuess"):
        lines += [f"[routes.{feature}]", "enabled = false"]
    path = tmp_path / "ai.toml"
    path.write_text("\n".join(lines))
    return load_ai_settings(
        {"AI_CONFIG_FILE": str(path), **{f"KEY_{cid.upper()}": f"sk-{cid}" for cid in groups}}
    )


def test_runtime_shares_pool_and_clients_across_features(tmp_path, monkeypatch):
    seen = []
    failures = {"sk-a": error(Code.PROVIDER_RATE_LIMITED, Scope.QUOTA, 60, 429)}

    def fake(key, config, **_options):
        seen.append(key)
        return FakeClient(key, config, failures)

    monkeypatch.setattr(registry, "OpenRouterTextClient", fake)
    runtime = AiRuntime(two_key_settings(tmp_path, {"a": "g1", "b": "g2"}), NoOpAITracer())
    translation = runtime.translator()._client
    clues = runtime.ispy_clue_generator()._client

    first = translation.generate(REQUEST)
    assert (first.route.credential_id, first.route.attempts) == ("b", 2)
    assert first.route.fallback_reason == "providerRateLimited"
    assert clues.generate(REQUEST).route.credential_id == "b"
    assert translation.generate(REQUEST).route.attempts == 1

    health = runtime.provider_pool.credentials.health(HealthScope.QUOTA_GROUP, "g1")
    assert health.reason is HealthReason.RATE_LIMITED
    assert seen.count("sk-a") == 1
    assert seen.count("sk-b") == 1
