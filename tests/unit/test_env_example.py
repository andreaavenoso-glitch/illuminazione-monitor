"""The settings classes must load the .env a new Codespace is built from.

setup.sh copies .env.example to .env, so any line there that a settings class
cannot parse stops the API (or the worker) at startup -- which is exactly what an
empty ANTHROPIC_BUDGET_USD= did. Loading the real file here catches that class of
mistake before it reaches a Codespace.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Only the file under test may supply values.
    import os

    for key in list(os.environ):
        if key.startswith(("ANTHROPIC_", "SMTP_", "POSTGRES_", "S3_", "CELERY_", "ENABLED_", "WEB_", "CRAWL_", "SCAN_")):
            monkeypatch.delenv(key, raising=False)


def test_api_settings_load_env_example() -> None:
    from app.core.config import Settings

    s = Settings(_env_file=str(ENV_EXAMPLE))
    assert s.anthropic_budget_usd is None
    assert s.anthropic_model


def test_worker_settings_load_env_example() -> None:
    from app.config import WorkerSettings

    s = WorkerSettings(_env_file=str(ENV_EXAMPLE))
    assert s.smtp_host == "" and s.enabled_services == ""
    assert s.anthropic_price_input_per_mtok == 0.0


def test_an_empty_budget_is_no_budget_and_a_number_is_a_number(monkeypatch, tmp_path) -> None:
    from app.core.config import Settings

    empty = tmp_path / "empty.env"
    empty.write_text("ANTHROPIC_BUDGET_USD=\n")
    assert Settings(_env_file=str(empty)).anthropic_budget_usd is None
    full = tmp_path / "full.env"
    full.write_text("ANTHROPIC_BUDGET_USD=50\n")
    assert Settings(_env_file=str(full)).anthropic_budget_usd == 50.0
