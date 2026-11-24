"""Record the tokens and estimated cost of every successful Anthropic call.

The scan sets ``current_run_id`` / ``current_scan_item_id`` (context variables:
each concurrent comune task has its own), so a call is attributed to the run and
the comune it was made for without passing ids through every function.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from app.config import get_worker_settings
from app.db import SessionLocal
from shared_models import ApiUsage
from shared_models.pricing import WEB_SEARCH_USD, cost_usd

log = logging.getLogger(__name__)

current_run_id: ContextVar[UUID | None] = ContextVar("current_run_id", default=None)
current_scan_item_id: ContextVar[UUID | None] = ContextVar("current_scan_item_id", default=None)


def usage_row(usage: Any, *, model: str, purpose: str, label: str | None) -> dict:
    """The api_usage values for a response's ``usage`` (pure, tested)."""
    s = get_worker_settings()
    override = (s.anthropic_price_input_per_mtok, s.anthropic_price_output_per_mtok)
    counts = {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    }
    searches = int(getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0)
    return {
        "model": model,
        "purpose": purpose,
        "label": (label or "")[:200] or None,
        **counts,
        "cost_usd": round(cost_usd(model, override=override, **counts) + searches * WEB_SEARCH_USD, 6),
    }


async def record_usage(usage: Any, *, model: str, purpose: str, label: str | None = None) -> None:
    """Never raises: a failure to write the counter must not fail the scan."""
    try:
        row = usage_row(usage, model=model, purpose=purpose, label=label)
        async with SessionLocal() as s:
            s.add(ApiUsage(run_id=current_run_id.get(), scan_item_id=current_scan_item_id.get(), **row))
            await s.commit()
        from app import claude_health

        await claude_health.note_success()
    except Exception:  # noqa: BLE001
        log.exception("usage.record_failed")
