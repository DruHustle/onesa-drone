"""Real ASGI request boundaries with no provider or hardware access."""

import asyncio

import pytest

from backend.app import main
from backend.app.config import Settings


def request_scope(config, headers=()):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/login",
        "query_string": b"",
        "headers": [(b"origin", config.origin.encode()), *headers],
        "server": ("127.0.0.1", 3400),
        "client": ("127.0.0.1", 12345),
    }


@pytest.mark.parametrize("trickle", [False, True])
def test_incomplete_body_has_a_total_deadline(tmp_path, monkeypatch, trickle):
    cfg = Settings(database_url=f"sqlite:///{tmp_path}/body.db", worker=False)
    app = main.create_app(cfg)
    monkeypatch.setattr(main, "REQUEST_BODY_SECONDS", 0.03, raising=False)
    messages = []

    async def receive():
        await asyncio.sleep(0.01 if trickle else 1)
        return {"type": "http.request", "body": b"x", "more_body": True}

    async def send(message):
        messages.append(message)

    async def run():
        async with asyncio.timeout(0.25):
            await app(request_scope(cfg), receive, send)

    asyncio.run(run())
    assert messages[0]["status"] == 408
    assert dict(messages[0]["headers"])[b"cache-control"] == b"no-store"
    assert app.state.health["requests"] == 1


@pytest.mark.parametrize(
    "length", [b"16385", b"-1", b"\xb2", b"9" * 5000], ids=["oversize", "negative", "nonascii", "huge"]
)
def test_invalid_or_excessive_content_length_is_rejected_before_reading(tmp_path, length):
    cfg = Settings(database_url=f"sqlite:///{tmp_path}/body.db", worker=False)
    app = main.create_app(cfg)
    messages = []

    async def receive():
        raise AssertionError("Rejected request length must not consume body bytes")

    async def send(message):
        messages.append(message)

    asyncio.run(app(request_scope(cfg, [(b"content-length", length)]), receive, send))
    assert messages[0]["status"] == 413
    assert dict(messages[0]["headers"])[b"cache-control"] == b"no-store"


def test_chunked_body_limit_does_not_depend_on_content_length(tmp_path):
    cfg = Settings(database_url=f"sqlite:///{tmp_path}/body.db", worker=False)
    app = main.create_app(cfg)
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"x" * 8193, "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(app(request_scope(cfg), receive, send))
    assert messages[0]["status"] == 413
    assert dict(messages[0]["headers"])[b"cache-control"] == b"no-store"
