import pytest
from backend.app.config import Settings


@pytest.mark.parametrize(
    "settings",
    [
        Settings(origin="https://console.example.test", secure=False, database_url="sqlite:///test.db"),
        Settings(
            origin="https://console.example.test",
            secure=True,
            database_url="postgresql+psycopg://localhost/drone?sslmode=require",
        ),
        Settings(origin="https://user:secret@example.test", secure=True),
        Settings(origin="http://127.0.0.1:3400/unsafe-path"),
    ],
)
def test_insecure_or_ambiguous_hosted_configuration_rejected(settings):
    with pytest.raises(ValueError):
        settings.validate()


def test_verified_hosted_database_configuration_accepted():
    Settings(
        origin="https://console.example.test",
        secure=True,
        database_url="postgresql+psycopg://db.example.test/drone?sslmode=verify-full",
    ).validate()
