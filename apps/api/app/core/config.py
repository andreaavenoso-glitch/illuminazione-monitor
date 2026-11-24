from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"

    # Optional company template (.pptx) for the slides of an opportunity: its master (logo, background) is kept.
    ppt_template_path: str = ""
    # Texts of the "Gate 1" sheet that belong to the user, not to the opportunity (city of the cover, author, owners).
    ppt_citta: str = ""
    ppt_autore: str = ""
    ppt_resp_commerciale: str = ""
    ppt_resp_tecnico: str = ""
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "lighting_monitor"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    redis_url: str = "redis://redis:6379/0"

    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"
    s3_bucket: str = "documents"
    s3_region: str = "us-east-1"

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"
    celery_timezone: str = "Europe/Rome"

    cors_origins: str = Field(default="http://localhost:3000")

    jwt_secret: str = Field(
        default="dev-only-secret-change-in-production-with-32-plus-chars!!"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 12  # 12h

    # Cost counter (see shared_models.pricing). The budget is optional: set it to
    # your Anthropic spending limit to see how much of it this app has used.
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_budget_usd: float | None = None
    anthropic_price_input_per_mtok: float = 0.0
    anthropic_price_output_per_mtok: float = 0.0

    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    @field_validator("anthropic_budget_usd", mode="before")
    @classmethod
    def _empty_budget_is_none(cls, v):
        # .env.example ships ANTHROPIC_BUDGET_USD= (empty = no budget): an empty
        # string must not be parsed as a number, or the API cannot even start.
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
