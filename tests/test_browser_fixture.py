"""Browser fixture sign-ins must not depend on crossing a rate-limit minute."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from scripts.browser_fixture import seed_browser_accounts


@pytest.mark.parametrize(
    ("accounts", "statuses"),
    [
        (
            [
                "flight-preview",
                "flight-session",
                "flight-session",
                "delivery",
                "navigation-light-390",
                "navigation-light-768",
                "navigation-light-1440",
                "navigation-dark-390",
                "navigation-dark-768",
                "navigation-dark-1440",
            ],
            [200] * 10,
        ),
        (["delivery"] * 7, [200] * 6 + [429]),
    ],
    ids=["all-scenarios-in-one-minute", "one-account-remains-rate-limited"],
)
def test_browser_fixture_signin_limits(tmp_path, monkeypatch, accounts, statuses):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path}/browser.db", worker=False))
    app.state.store.initialize()
    seed_browser_accounts(app.state.store)
    # Freeze only the limiter clock, so this regression cannot accidentally pass
    # because a slow runner crossed a wall-clock minute during the sign-ins.
    monkeypatch.setattr("backend.app.security.time", SimpleNamespace(time=lambda: 1800000000))
    with TestClient(app) as client:
        responses = [
            client.post(
                "/api/v1/auth/login",
                headers={"Origin": app.state.settings.origin},
                json={
                    "email": f"browser-{account}@example.test",
                    "password": "Synthetic-browser-password-42!",
                },
            )
            for account in accounts
        ]
        assert [response.status_code for response in responses] == statuses
        if statuses[-1] == 429:
            assert responses[-1].json()["detail"] == "Request limit reached; retry after one minute"
