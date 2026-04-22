import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.core.storage import get_s3_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    result = {"status": "ok", "db": "unknown", "redis": "unknown", "s3": "unknown"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception as e:
        result["db"] = f"error: {e!s}"
        result["status"] = "degraded"

    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        result["redis"] = "ok"
    except Exception as e:
        result["redis"] = f"error: {e!s}"
        result["status"] = "degraded"

    try:
        def _list() -> None:
            get_s3_client().head_bucket(Bucket=settings.s3_bucket)

        await asyncio.to_thread(_list)
        result["s3"] = "ok"
    except Exception as e:
        result["s3"] = f"error: {e!s}"
        result["status"] = "degraded"

    return result
