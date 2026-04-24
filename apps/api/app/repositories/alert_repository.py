from datetime import UTC, datetime
from uuid import UUID

from shared_models import Alert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, alert_id: UUID) -> Alert | None:
        return await self.session.get(Alert, alert_id)

    async def list(
        self,
        *,
        is_open: bool | None = None,
        severity: str | None = None,
        limit: int = 200,
    ) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.opened_at.desc()).limit(limit)
        if is_open is not None:
            stmt = stmt.where(Alert.is_open == is_open)
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        return list((await self.session.execute(stmt)).scalars().all())

    async def close(self, alert_id: UUID) -> Alert | None:
        alert = await self.get(alert_id)
        if alert is None:
            return None
        alert.is_open = False
        alert.closed_at = datetime.now(tz=UTC)
        await self.session.flush()
        return alert
