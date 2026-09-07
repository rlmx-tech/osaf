from pydantic import field_validator
from pydantic_settings import BaseSettings

# HS256 signs every JWT with this value, so a guessable one lets anyone forge a
# token with "role": "admin". Compose's ${SECRET_KEY:?...} only catches unset or
# empty — it happily accepts the placeholder shipped in .env.example.
MIN_SECRET_KEY_LENGTH = 32

# Placeholders from .env.example and deploy/.env.example. An operator who copies
# the template and forgets to substitute must not get a running, signable app.
_REJECTED_SECRET_PREFIXES = ("changeme", "change-me", "your-secret", "replace-me")


class Settings(BaseSettings):
    # Database
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "osaf"
    postgres_user: str = "osaf"
    postgres_password: str

    # Auth
    secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Ollama Cloud (used by the LLM near-dupe batch job)
    ollama_url: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = "glm-5.2:cloud"
    ollama_timeout: int = 300

    # Environment: "development" disables cookie Secure flag and OpenAPI gate
    app_env: str = "production"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("secret_key")
    @classmethod
    def _reject_weak_secret_key(cls, value: str) -> str:
        """Refuse to start on a short or placeholder signing key.

        Failing at import is deliberate: a weak key produces an app that looks
        healthy while every token it issues is forgeable, which is far worse
        than a container that will not boot.
        """
        if len(value) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters "
                f"(got {len(value)}). Generate one with: openssl rand -hex 32"
            )
        if value.strip().lower().startswith(_REJECTED_SECRET_PREFIXES):
            raise ValueError(
                "SECRET_KEY is still the example placeholder. Generate a real "
                "one with: openssl rand -hex 32"
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        # Load local dev settings from backend/.env. OS environment variables
        # still take precedence (e.g. Docker Compose), so this is a no-op in prod.
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
