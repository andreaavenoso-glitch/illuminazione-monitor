from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    procurement_record_id: UUID | None
    source_id: UUID | None
    filename: str | None
    mime_type: str | None
    storage_url: str
    text_content: str | None
    checksum: str | None
    created_at: datetime


class DocumentIngestRequest(BaseModel):
    """Request to fetch a remote document and store it in object storage."""

    procurement_record_id: UUID
    url: str
    filename: str | None = None
