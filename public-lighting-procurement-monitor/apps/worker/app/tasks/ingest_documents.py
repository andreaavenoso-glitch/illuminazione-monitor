"""Fetch a remote document, upload to MinIO, persist a Document row.

Triggered manually via POST /documents/ingest from the API. Skipped if a
document with the same checksum already exists for the record.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from urllib.parse import urlparse
from uuid import UUID

import httpx
from app.celery_app import celery_app
from app.db import SessionLocal
from app.storage import build_object_key, upload_bytes
from shared_models import Document, JobRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else "document"
    return name or "document"


async def _existing_for_checksum(
    session: AsyncSession, *, record_id: UUID, checksum: str
) -> Document | None:
    stmt = select(Document).where(
        Document.procurement_record_id == record_id,
        Document.checksum == checksum,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _run(record_id: UUID, url: str, filename: str | None) -> dict:
    async with SessionLocal() as session:
        job = JobRun(job_name="ingest_document", status="running")
        session.add(job)
        await session.flush()

        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                body = response.content
                if len(body) > MAX_BYTES:
                    raise ValueError(f"document too large: {len(body)} bytes")
                content_type = response.headers.get("content-type")

            checksum = hashlib.sha256(body).hexdigest()
            existing = await _existing_for_checksum(session, record_id=record_id, checksum=checksum)
            if existing is not None:
                job.status = "success"
                job.records_found = 1
                job.records_valid = 0
                job.ended_at = job.ended_at  # noqa: PLW0127 — keep server default
                await session.commit()
                return {"status": "skipped", "document_id": str(existing.id)}

            obj_key = build_object_key(record_id, filename or _filename_from_url(url))
            storage_url = upload_bytes(body=body, object_key=obj_key, content_type=content_type)

            doc = Document(
                procurement_record_id=record_id,
                source_id=None,
                filename=filename or _filename_from_url(url),
                mime_type=content_type,
                storage_url=storage_url,
                text_content=None,
                checksum=checksum,
            )
            session.add(doc)
            await session.flush()

            job.status = "success"
            job.records_found = 1
            job.records_valid = 1
            await session.commit()
            return {"status": "stored", "document_id": str(doc.id), "storage_url": storage_url}
        except Exception as exc:  # noqa: BLE001
            log.exception("ingest_document.crashed", extra={"url": url, "err": str(exc)})
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"
            await session.commit()
            raise


@celery_app.task(name="app.tasks.ingest_documents.ingest_document")
def ingest_document(record_id: str, url: str, filename: str | None = None) -> dict:
    return asyncio.run(_run(UUID(record_id), url, filename))
