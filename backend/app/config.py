from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./drone.db")
    origin: str = os.getenv("APP_ORIGIN", "http://127.0.0.1:3400")
    secure: bool = os.getenv("COOKIE_SECURE", "false") == "true"
    worker: bool = os.getenv("SIMULATION_WORKER", "true") == "true"
    session_seconds: int = 3600
    telemetry_limit: int = 600
    ai_url: str = os.getenv("ONESA_AI_URL", "")
    ai_provider: str = os.getenv("ONESA_AI_PROVIDER", "onesa-legacy")
    ai_model: str = os.getenv("ONESA_AI_MODEL", "default")
    ai_api_key: str = field(default=os.getenv("ONESA_AI_API_KEY", ""), repr=False)
    ai_session: str = field(default=os.getenv("ONESA_AI_DELEGATED_SESSION", ""), repr=False)
    ai_csrf: str = field(default=os.getenv("ONESA_AI_DELEGATED_CSRF", ""), repr=False)
    ai_origin: str = os.getenv("ONESA_AI_ORIGIN", "")
    ai_tenant: str = os.getenv("ONESA_AI_TENANT_ID", "")
    ai_cookie: str = os.getenv("ONESA_AI_COOKIE_NAME", "onesa_session")

    def validate(self):
        origin = urlsplit(self.origin)
        if (
            not origin.hostname
            or origin.username
            or origin.password
            or self.origin != f"{origin.scheme}://{origin.netloc}"
        ):
            raise ValueError("APP_ORIGIN must be an exact origin without path or credentials")
        if not self.origin.startswith(("http://127.0.0.1:", "http://localhost:")):
            if (
                not self.origin.startswith("https://")
                or not self.secure
                or self.database_url.startswith("sqlite:")
            ):
                raise ValueError("Hosted operation requires HTTPS, secure cookies and PostgreSQL")
            database = make_url(self.database_url)
            if database.drivername != "postgresql+psycopg" or database.query.get("sslmode") != "verify-full":
                raise ValueError("Hosted PostgreSQL requires psycopg and sslmode=verify-full")
        if self.ai_provider not in {"disabled", "onesa-legacy", "onesa", "openai-compatible"}:
            raise ValueError("Unknown AI provider")
        if self.ai_url:
            from integrations.ai.consumer import https_base

            https_base(self.ai_url)
