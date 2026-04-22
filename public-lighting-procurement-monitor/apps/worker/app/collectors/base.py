from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from parsing_rules import is_in_lighting_perimeter
from shared_models import RawRecord
from sqlalchemy.ext.asyncio import AsyncSession


class CollectorError(Exception):
    pass


@dataclass
class RawRecordDraft:
    raw_url: str
    raw_title: str | None = None
    raw_body: str | None = None
    raw_html: str | None = None
    raw_date: datetime | None = None
    extracted: dict[str, Any] = field(default_factory=dict)

    def checksum(self) -> str:
        payload = f"{self.raw_url}|{self.raw_title or ''}|{self.raw_date or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CollectorResult:
    found: int = 0
    valid: int = 0
    weak: int = 0
    duplicates_removed: int = 0
    error: str | None = None


class BaseCollector(ABC):
    name: str = "base"

    def __init__(self, source_id: UUID, base_url: str, *, timeout: float = 45.0):
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @abstractmethod
    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        """Fetch candidate records from the source. Should filter to lighting scope already."""

    async def persist(
        self,
        session: AsyncSession,
        drafts: list[RawRecordDraft],
    ) -> CollectorResult:
        result = CollectorResult(found=len(drafts))
        seen: set[str] = set()
        for draft in drafts:
            combined = " ".join(filter(None, [draft.raw_title, draft.raw_body]))
            if not is_in_lighting_perimeter(combined):
                continue
            checksum = draft.checksum()
            if checksum in seen:
                result.duplicates_removed += 1
                continue
            seen.add(checksum)
            session.add(
                RawRecord(
                    source_id=self.source_id,
                    raw_title=draft.raw_title,
                    raw_body=draft.raw_body,
                    raw_html=draft.raw_html,
                    raw_url=draft.raw_url,
                    raw_date=draft.raw_date or datetime.now(tz=UTC),
                    extracted_json=draft.extracted or None,
                    checksum=checksum,
                )
            )
            result.valid += 1
        return result

    async def run(self, session: AsyncSession, *, since: datetime | None = None) -> CollectorResult:
        try:
            drafts = await self.fetch(since=since)
        except Exception as exc:  # noqa: BLE001
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
        return await self.persist(session, drafts)
