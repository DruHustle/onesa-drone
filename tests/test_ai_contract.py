import asyncio
import json
from types import SimpleNamespace
from integrations.onesa_ai.adapter import advise
import httpx


def test_existing_platform_conversation_and_csrf_contract(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["Origin"] == "https://ai.example.test"
        assert request.headers["X-CSRF-Token"] == "synthetic-test-csrf"
        assert "onesa_session=synthetic-test-session" in request.headers["Cookie"]
        if request.url.path == "/api/v1/conversations":
            return httpx.Response(201, json={"id": "synthetic-conversation"})
        data = json.loads(request.content)
        assert (
            data["conversation_id"] == "synthetic-conversation"
            and data["model_id"] == "default"
            and data["stream"] is True
        )
        assert "secret-route" not in data["content"] and "secret-user" not in data["content"]
        return httpx.Response(
            200,
            text='event: content_delta\ndata: {"text":"Advisory response."}\n\nevent: message_end\ndata: {}\n\n',
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    cfg = SimpleNamespace(
        ai_url="https://api.example.test",
        ai_session="synthetic-test-session",
        ai_csrf="synthetic-test-csrf",
        ai_origin="https://ai.example.test",
        ai_tenant="tenant",
        ai_cookie="onesa_session",
    )
    context = {
        "counts": {},
        "aircraft": [],
        "missions": [
            {
                "state": "completed",
                "scenario": "nominal",
                "plan": {},
                "destination": "secret-route",
                "user": "secret-user",
            }
        ],
    }
    result = asyncio.run(advise("Explain", context, cfg, "tenant"))
    assert result["answer"] == "Advisory response." and result["source"] == "onesa-ai-platform"
    assert len(calls) == 2
    calls.clear()
    result = asyncio.run(advise("Explain", context, cfg, "other"))
    assert result["provider_status"] == "not-configured" and not calls
