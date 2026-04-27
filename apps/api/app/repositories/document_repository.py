from uuid import UUID

from shared_models import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, document_id: UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def list_for_record(self, record_id: UUID) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.procurement_record_id == record_id)
            .order_by(Document.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add(
        self,
        *,
        procurement_record_id: UUID,
        source_id: UUID | None,
        filename: str,
        mime_type: str | None,
        storage_url: str,
        text_content: str | None,
        checksum: str | None,
    ) -> Document:
        doc = Document(
            procurement_record_id=procurement_record_id,
            source_id=source_id,
            filename=filename,
            mime_type=mime_type,
            storage_url=storage_url,
            text_content=text_content,
            checksum=checksum,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc
