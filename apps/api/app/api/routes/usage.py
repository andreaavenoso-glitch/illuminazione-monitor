"""Estimated spend on the Anthropic API (see shared_models.pricing)."""
from datetime import UTC, datetime, timedelta

from app.auth import current_user
from app.core.config import get_settings
from app.core.database import get_session
from fastapi import APIRouter, Depends
from shared_models import ApiUsage, User
from shared_models.pricing import PRICES, price_for
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _f(x) -> float:
    return round(float(x or 0), 4)


@router.get("")
async def usage_summary(
    _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    now = datetime.now(tz=UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    settings = get_settings()

    async def window(since: datetime | None) -> dict:
        stmt = select(
            func.coalesce(func.sum(ApiUsage.cost_usd), 0),
            func.count(),
            func.coalesce(func.sum(ApiUsage.input_tokens + ApiUsage.cache_read_tokens + ApiUsage.cache_write_tokens), 0),
            func.coalesce(func.sum(ApiUsage.output_tokens), 0),
        )
        if since is not None:
            stmt = stmt.where(ApiUsage.created_at >= since)
        cost, calls, tin, tout = (await session.execute(stmt)).one()
        return {"cost_usd": _f(cost), "calls": int(calls), "input_tokens": int(tin), "output_tokens": int(tout)}

    days = (
        await session.execute(
            select(func.date_trunc("day", ApiUsage.created_at).label("d"), func.sum(ApiUsage.cost_usd), func.count())
            .where(ApiUsage.created_at >= today - timedelta(days=13))
            .group_by("d").order_by("d")
        )
    ).all()
    by_day = {d.date().isoformat(): (_f(c), int(n)) for d, c, n in days}
    series = []
    for k in range(13, -1, -1):
        key = (today - timedelta(days=k)).date().isoformat()
        cost, calls = by_day.get(key, (0.0, 0))
        series.append({"day": key, "cost_usd": cost, "calls": calls})

    async def grouped(column) -> list[dict]:
        rows = (
            await session.execute(
                select(column, func.sum(ApiUsage.cost_usd), func.count())
                .where(ApiUsage.created_at >= month).group_by(column).order_by(func.sum(ApiUsage.cost_usd).desc())
            )
        ).all()
        return [{"name": n, "cost_usd": _f(c), "calls": int(k)} for n, c, k in rows]

    month_total = await window(month)
    p_in, p_out, known = price_for(
        settings.anthropic_model, (settings.anthropic_price_input_per_mtok, settings.anthropic_price_output_per_mtok)
    )
    budget = settings.anthropic_budget_usd
    return {
        "today": await window(today),
        "month": month_total,
        "total": await window(None),
        "days": series,
        "by_purpose": await grouped(ApiUsage.purpose),
        "by_model": await grouped(ApiUsage.model),
        "budget": None if budget is None else {
            "limit_usd": budget, "spent_usd": month_total["cost_usd"],
            "remaining_usd": round(budget - month_total["cost_usd"], 4),
        },
        "pricing": {
            "model": settings.anthropic_model, "input_per_mtok": p_in, "output_per_mtok": p_out,
            "model_in_table": known, "table": {k: list(v) for k, v in PRICES.items()},
        },
    }
