"""Provider-neutral advisory, tenant and completed-stream regressions."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from backend.app.config import Settings
from integrations.ai.consumer import CONTRACT_VERSION, CompletionError
from integrations.onesa_ai.adapter import advise, configured, legacy_text

CONTEXT = {
    "counts": {"paused": 1},
    "aircraft": [{"name": "private-name", "category": "multirotor", "battery": 50, "status": "available"}],
    "missions": [
        {
            "state": "paused",
            "scenario": "nominal",
            "plan": {"distance_m": 12, "private": "private-plan"},
            "destination": "private-destination",
            "user": "private-user",
        }
    ],
}


def config(provider="onesa"):
    return Settings(
        ai_provider=provider,
        ai_url="https://provider.example.test",
        ai_session="synthetic-session",
        ai_csrf="synthetic-csrf",
        ai_origin="https://console.example.test",
        ai_tenant="tenant",
        ai_model="default",
        ai_api_key="synthetic-key",
    )


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)


def test_same_drone_advisory_uses_either_provider_without_business_logic_changes(monkeypatch):
    messages, paths = [], []

    def handle(request):
        paths.append(request.url.path)
        body = json.loads(request.content)
        messages.append(body["messages"])
        text = json.dumps(body)
        for private in ("private-name", "private-plan", "private-destination", "private-user"):
            assert private not in text
        assert "tools" not in body and "launch" not in body
        if request.url.path == "/api/v1/inference/completions":
            assert "Authorization" not in request.headers
            return httpx.Response(
                200,
                json={
                    "contract_version": CONTRACT_VERSION,
                    "outcome": "completed",
                    "text": "Read-only advisory",
                    "model": {"model_identifier": "mock-model", "real_inference": False},
                },
            )
        assert request.headers["Authorization"] == "Bearer synthetic-key"
        assert "Cookie" not in request.headers and "X-CSRF-Token" not in request.headers
        return httpx.Response(
            200,
            json={
                "model": "other-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Read-only advisory"},
                    }
                ],
            },
        )

    install_transport(monkeypatch, handle)
    first = asyncio.run(advise("Explain current operations", CONTEXT, config(), "tenant"))
    second = asyncio.run(
        advise(
            "Explain current operations",
            CONTEXT,
            replace(config("openai-compatible"), ai_url="https://other.example.test/v1"),
            "tenant",
        )
    )
    assert first["answer"] == second["answer"] == "Read-only advisory"
    assert first["advisory_only"] and second["advisory_only"]
    assert messages[0] == messages[1]
    assert paths == ["/api/v1/inference/completions", "/v1/chat/completions"]
    assert first["provenance"]["model"] == "mock-model" and second["provenance"]["model"] == "other-model"
    assert first["provenance"]["contract_version"] == CONTRACT_VERSION


@pytest.mark.parametrize("provider", ["onesa", "onesa-legacy", "openai-compatible", "disabled"])
def test_other_tenant_never_uses_a_delegated_provider(monkeypatch, provider):
    def forbidden(_):
        pytest.fail("A foreign tenant must never use this provider identity")

    install_transport(monkeypatch, forbidden)
    result = asyncio.run(advise("Explain", CONTEXT, config(provider), "other-tenant"))
    assert result["provider_status"] == "not-configured"
    assert result["source"] == "deterministic-operational-summary"


@pytest.mark.parametrize("status", [401, 403, 429, 503, 307])
def test_provider_failure_has_one_attempt_and_explicit_local_summary(monkeypatch, status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"Location": "https://foreign.example.test"}, text="private-provider-error"
        )

    install_transport(monkeypatch, handle)
    result = asyncio.run(advise("Explain", CONTEXT, config("openai-compatible"), "tenant"))
    assert len(calls) == 1 and result["provider_status"] == "unavailable-or-contract-unqualified"
    assert result["source"] == "deterministic-operational-summary"
    assert "private-provider-error" not in json.dumps(result)


@pytest.mark.parametrize(
    "tail",
    [
        "",
        'event: error\ndata: {"message":"failed"}\n\n',
        "event: message_cancelled\ndata: {}\n\n",
        'event: content_delta\ndata: {"text":42}\n\n',
    ],
)
def test_partial_or_cancelled_legacy_stream_is_rejected(tail):
    with pytest.raises(CompletionError):
        legacy_text(('event: content_delta\ndata: {"text":"partial"}\n\n' + tail).encode())


def test_complete_legacy_stream_and_oversize_are_distinguished():
    assert (
        legacy_text(b'event: content_delta\ndata: {"text":"complete"}\n\nevent: message_end\ndata: {}\n\n')
        == "complete"
    )
    with pytest.raises(CompletionError):
        legacy_text(
            (
                "event: content_delta\ndata: "
                + json.dumps({"text": "x" * 8001})
                + "\n\nevent: message_end\ndata: {}\n\n"
            ).encode()
        )


def test_disabled_and_partial_configuration_are_truthful():
    assert not configured(config("disabled"))
    assert not configured(replace(config(), ai_csrf=""))
    assert not configured(replace(config("openai-compatible"), ai_api_key=""))
    assert "synthetic-key" not in repr(config("openai-compatible"))
    assert "synthetic-session" not in repr(config())


@pytest.mark.parametrize(
    "url",
    [
        "http://local.test",
        "https://user:password@host.test",
        "https://host.test?token=private",
        "https://host.test#x",
    ],
)
def test_invalid_server_endpoint_fails_before_application_start(url):
    with pytest.raises(ValueError):
        replace(config(), ai_url=url).validate()
