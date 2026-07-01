from pydantic_settings import BaseSettings


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
