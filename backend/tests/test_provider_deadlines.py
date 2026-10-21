"""Total deadlines cancel I/O and finish cleanup before routing another call."""

import asyncio
import json
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from test_routing import REQUEST, Clock, FakeProvider, Route, ok_body

from app.ai.adapters.gemini import GeminiTextClient
from app.ai.adapters.openai import OpenAITextClient
from app.ai.contracts.errors import ProviderError, ProviderErrorCode
from app.ai.contracts.text import TextModelConfig
from app.ai.routing import InvocationContext, RoutedModelClient, RouteTarget
from app.ai.routing.router import FixedCredential


@pytest.mark.parametrize("stage", ["acquire", "build"])
@pytest.mark.parametrize("elapsed", [4, 10, 11])
def test_client_setup_reduces_deadline_without_spending_outbound_calls(stage, elapsed):
    clock = Clock()
    route = Route({"primary": ["a"]}, deadline=10, clock=clock)
    if stage == "acquire":
        original = route.credentials.acquire

        def acquire(*args):
            clock.now += elapsed
            return original(*args)

        route.credentials.acquire = acquire
    else:
        target = route.client._targets[0]

        def build(secret):
            clock.now += elapsed
            return target.build(secret)

        route.client._targets = (replace(target, build=build),)
    invocation = route.client.start_invocation()
    if elapsed >= 10:
        with pytest.raises(ProviderError) as raised:
            route.client.generate(REQUEST, invocation)
        assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
        assert invocation.calls == 0
        assert route.order == []
    else:
        route.client.generate(REQUEST, invocation)
        assert invocation.calls == 1
        assert route.providers[("primary", "a")].calls == [pytest.approx(6)]


def test_router_rejects_late_success_and_does_not_start_replacement():
    route = Route({"primary": ["a"], "backup": ["b"]}, deadline=5, advance=6)
    invocation = route.client.start_invocation()
    with pytest.raises(ProviderError) as raised:
        route.client.generate(REQUEST, invocation)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert invocation.calls == 1
    assert route.order == [("primary", "a")]
    calls = [record for record in route.tracer.records if record["name"] == "model-call"]
    assert calls[0]["updates"][0]["error_code"] == "providerTimeout"


class SlowChunks(httpx.AsyncByteStream):
    def __init__(self):
        self.chunks = 0
        self.cancelled = False
        self.closed = False

    async def __aiter__(self):
        try:
            for chunk in json.dumps(ok_body()).encode():
                await asyncio.sleep(0.01)
                self.chunks += 1
                yield bytes([chunk])
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        await asyncio.sleep(0.01)
        self.closed = True


def test_slow_response_chunks_are_cancelled_and_closed_at_total_deadline():
    stream = SlowChunks()
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    )
    client = OpenAITextClient("key", TextModelConfig(model_name="m"), client=http)
    start = time.monotonic()
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST, timeout_seconds=0.08)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert stream.cancelled and stream.closed
    assert 0 < stream.chunks < len(json.dumps(ok_body()))
    assert time.monotonic() - start < 1


def test_replacement_waits_for_cancelled_response_cleanup():
    stream = SlowChunks()
    primary = OpenAITextClient(
        "key",
        TextModelConfig(model_name="m", timeout_seconds=0.05),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
        ),
    )
    replacement = FakeProvider()
    original = replacement.generate

    def generate(*args, **kwargs):
        assert stream.cancelled and stream.closed
        return original(*args, **kwargs)

    replacement.generate = generate
    route = RoutedModelClient(
        "text",
        (
            RouteTarget("primary", "openai", primary._config, lambda key: primary),
            RouteTarget("backup", "fake", TextModelConfig(model_name="m"), lambda key: replacement),
        ),
        FixedCredential(),
        max_model_calls=2,
        deadline_seconds=2,
    )
    invocation = route.start_invocation()
    result = route.generate(REQUEST, invocation)
    assert result.route.deployment_id == "backup"
    assert invocation.calls == 2
    assert len(replacement.calls) == 1


def test_responses_transport_that_returns_after_cancellation_is_rejected():
    async def handler(request):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return httpx.Response(200, json=ok_body())

    client = OpenAITextClient(
        "key",
        TextModelConfig(model_name="m"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST, timeout_seconds=0.03)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT


@pytest.mark.parametrize("suppress_cancellation", [False, True])
def test_gemini_io_is_cancelled_and_late_success_rejected(suppress_cancellation):
    state = {"active": False, "cancelled": False, "cleaned": False}

    async def generate_content(**kwargs):
        state["active"] = True
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            state["cancelled"] = True
            if suppress_cancellation:
                return SimpleNamespace(text="{}")
            raise
        finally:
            await asyncio.sleep(0.01)
            state["active"] = False
            state["cleaned"] = True

    client = GeminiTextClient(
        "key",
        TextModelConfig(model_name="m"),
        client=SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        ),
    )
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST, timeout_seconds=0.03)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert state == {"active": False, "cancelled": True, "cleaned": True}


@pytest.mark.parametrize("adapter", ["responses", "gemini"])
def test_adapter_rechecks_shared_deadline_after_request_preparation(adapter, monkeypatch):
    clock = Clock()
    invocation = InvocationContext(1, deadline_seconds=5, clock=clock)
    seen = []
    if adapter == "responses":

        async def handler(request):
            seen.append(request)
            return httpx.Response(200, json=ok_body())

        client = OpenAITextClient(
            "key",
            TextModelConfig(model_name="m"),
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        original = client._request_body

        def body(*args):
            clock.now += 6
            return original(*args)

        monkeypatch.setattr(client, "_request_body", body)
    else:
        from app.ai.adapters import gemini

        async def generate_content(**kwargs):
            seen.append(kwargs)
            return SimpleNamespace(text="{}")

        def build():
            clock.now += 6
            return SimpleNamespace(
                aio=SimpleNamespace(
                    models=SimpleNamespace(generate_content=generate_content), aclose=aclose
                ),
                close=lambda: None,
            )

        async def aclose():
            pass

        client = gemini.GeminiTextClient("key", TextModelConfig(model_name="m"))
        monkeypatch.setattr(client, "_new_client", build)
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST, invocation=invocation)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert seen == []
    assert invocation.calls == 0


def test_shared_invocation_never_overlaps_calls():
    started, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    provider = FakeProvider()
    original = provider.generate
    active = 0
    lock = threading.Lock()

    def generate(*args, **kwargs):
        nonlocal active
        with lock:
            active += 1
            assert active == 1
        try:
            started.set()
            assert release.wait(2)
            return original(*args, **kwargs)
        finally:
            with lock:
                active -= 1

    provider.generate = generate
    route = RoutedModelClient(
        "text",
        (RouteTarget("primary", "fake", TextModelConfig(model_name="m"), lambda key: provider),),
        FixedCredential(),
        max_model_calls=2,
    )
    invocation = route.start_invocation()
    errors = []

    def call(second=False):
        if second:
            second_entered.set()
        try:
            route.generate(REQUEST, invocation)
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=call)
    second = threading.Thread(target=call, args=(True,))
    first.start()
    assert started.wait(2)
    second.start()
    assert second_entered.wait(2)
    release.set()
    first.join(2)
    second.join(2)
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert invocation.calls == 2


def test_real_gemini_sdk_cancels_slow_chunks_and_closes_transport(monkeypatch):
    from google import genai
    from google.genai import types

    stream = SlowChunks()
    client = GeminiTextClient("key", TextModelConfig(model_name="gemini-test"))

    sdk = genai.Client(
        api_key="key",
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1),
            async_client_args={
                "transport": httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
            },
        ),
    )
    monkeypatch.setattr(client, "_new_client", lambda: sdk)
    with pytest.raises(ProviderError) as raised:
        client.generate(REQUEST, timeout_seconds=0.08)
    assert raised.value.code is ProviderErrorCode.PROVIDER_TIMEOUT
    assert stream.cancelled and stream.closed


def test_implicit_route_deadline_matches_advertised_ispy_lease_bound():
    from app.ai.features.ispy_guess.service import ISpyGuessService
    from app.ai.observability import NoOpAITracer
    from app.repositories.postgres.workflow import (
        EVALUATION_LEASE_MARGIN_SECONDS,
        PostgresWorkflowRepository,
    )

    clock = Clock()
    config = TextModelConfig(model_name="m", timeout_seconds=7, max_retries=1)
    route = RoutedModelClient(
        "text",
        (RouteTarget("primary", "fake", config, lambda key: FakeProvider()),),
        FixedCredential(),
        max_model_calls=2,
        clock=clock,
    )
    guesser = ISpyGuessService(route, config, tracer=NoOpAITracer(), provider="fake")
    assert guesser.max_duration_seconds == 14
    invocation = route.start_invocation()
    assert invocation.remaining_seconds() == 14
    lease = PostgresWorkflowRepository._evaluation_lease(
        SimpleNamespace(ispy_guess_generator=guesser)
    )
    assert lease.total_seconds() == 14 + EVALUATION_LEASE_MARGIN_SECONDS


def test_ispy_schema_preparation_uses_lease_deadline(monkeypatch):
    from test_ispy_guess_service import CONTEXT, LEARNER_TEXT

    from app.ai.features.ispy_guess import service as module
    from app.ai.observability import NoOpAITracer

    clock = Clock()
    route = Route({"primary": ["a"]}, deadline=5, clock=clock)
    guesser = module.ISpyGuessService(
        route.client, TextModelConfig(model_name="m"), tracer=NoOpAITracer(), provider="fake"
    )
    original = module.build_strict_json_schema

    def schema(*args):
        clock.now += 6
        return original(*args)

    monkeypatch.setattr(module, "build_strict_json_schema", schema)
    with pytest.raises(module.ISpyGuessError):
        guesser.guess(CONTEXT, LEARNER_TEXT)
    assert route.order == []
