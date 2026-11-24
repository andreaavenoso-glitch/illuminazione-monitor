"""A one-token call that tells whether Claude is usable (credit, limit, key): about $0.00002."""
from __future__ import annotations

import asyncio

import anthropic
from app import claude_health
from app.celery_app import celery_app
from app.collectors.albo_pretorio_llm import is_fatal_api_error
from app.config import get_worker_settings
from app.usage import record_usage


async def probe() -> dict:
    s = get_worker_settings()
    if not s.anthropic_api_key:
        await claude_health.set_status(False, "chiave ANTHROPIC_API_KEY assente")
        return {"ok": False, "error": "chiave assente"}
    try:
        r = await anthropic.AsyncAnthropic(api_key=s.anthropic_api_key).messages.create(
            model=s.anthropic_model, max_tokens=1, messages=[{"role": "user", "content": "ok"}]
        )
    except anthropic.APIError as exc:
        if is_fatal_api_error(exc):
            await claude_health.set_status(False, str(exc)[:500])
            return {"ok": False, "error": str(exc)[:200]}
        return {"ok": None, "error": f"errore temporaneo: {str(exc)[:150]}"}  # unchanged
    await record_usage(r.usage, model=s.anthropic_model, purpose="health", label="probe")
    await claude_health.set_status(True)
    return {"ok": True}


@celery_app.task(name="app.tasks.claude_health.check_claude", soft_time_limit=60, time_limit=90)
def check_claude() -> dict:
    return asyncio.run(probe())
