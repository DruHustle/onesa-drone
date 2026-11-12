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


def test_hosted_drone_requires_portal_even_with_verified_database():
    with pytest.raises(ValueError, match="Company Portal"):
        Settings(
            origin="https://console.example.test",
            secure=True,
            database_url="postgresql+psycopg://db.example.test/drone?sslmode=verify-full",
        ).validate()


def test_verified_hosted_database_configuration_accepted():
    from cryptography.fernet import Fernet

    Settings(
        origin="https://console.example.test",
        secure=True,
        identity_enabled=True,
        identity_issuer="https://portal.example.test/api/v1/identity",
        identity_client_id="synthetic-drone",
        identity_client_secret="synthetic-test-only-" * 3,
        identity_callback="https://console.example.test/api/v1/auth/identity/callback",
        identity_encryption_key=Fernet.generate_key().decode("ascii"),
        database_url="postgresql+psycopg://db.example.test/drone?sslmode=verify-full",
    ).validate()
