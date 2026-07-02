from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "lighting_monitor"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"
    celery_timezone: str = "Europe/Rome"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    smart_collector_max_html_chars: int = 80000
    smart_collector_playwright_min_chars: int = 3000
    smart_collector_playwright_wait_ms: int = 4000

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


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
