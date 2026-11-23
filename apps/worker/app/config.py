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
    # auto | claude | rules: see app.claude_state (auto = Claude, free rules when it is unavailable)
    extraction_mode: str = "auto"
    # Referenti: "script" (default, free) = a program follows the 12-step checklist on the comune's own site,
    # IPA and the local press; "agent" = Claude researches the web instead (costs); "auto" = script first,
    # then the agent only if the script found no sindaco; "pagine" = the older reader of a few pages.
    referenti_mode: str = "script"
    referenti_model: str = "claude-sonnet-5-5"
    referenti_max_searches: int = 8
    referenti_max_fetches: int = 12
    # Override of the price table (USD per million tokens) for the cost counter; 0 = use the table.
    anthropic_price_input_per_mtok: float = 0.0
    anthropic_price_output_per_mtok: float = 0.0
    smart_collector_max_html_chars: int = 80000
    smart_collector_playwright_min_chars: int = 3000
    smart_collector_playwright_wait_ms: int = 4000

    # Services of the catalog (shared_models.services) to look for, comma-separated
    # keys; empty means all of them.
    enabled_services: str = ""

    # Deep crawl of one comune's site (see app.collectors.crawler).
    crawl_max_pages: int = 20
    crawl_max_depth: int = 5
    crawl_time_budget_s: float = 150.0
    # Hard ceiling for ONE comune (fetch + crawl + Claude + detail pages): a hung
    # browser or API call must not keep the whole scan running for hours.
    scan_item_timeout_s: float = 420.0
    # Pause between two requests to the same host, and comuni scanned at once.
    crawl_delay_s: float = 1.0
    scan_concurrency: int = 3
    # Hosts other than the comune's own (provincial portals, vendors) get less time.
    crawl_external_timeout_s: float = 25.0
    # Pages are fetched up to this size and read whole by the page gate; only
    # what is sent to Claude is cut to smart_collector_max_html_chars.
    crawl_max_html_chars: int = 600000

    # Outbound email for the regional digests. Empty smtp_host = email off:
    # digests are built and logged but never marked as sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    web_base_url: str = "http://localhost:3000"

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
