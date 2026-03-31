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

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
