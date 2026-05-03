from uuid import UUID

from app.auth import current_user, require_role
from app.core.database import get_session
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentIngestRequest, DocumentRead
from fastapi import APIRouter, Depends, HTTPException
from shared_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/by-record/{record_id}", response_model=list[DocumentRead])
async def list_documents_for_record(
    record_id: UUID,
    _: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentRead]:
    repo = DocumentRepository(session)
    items = await repo.list_for_record(record_id)
    return [DocumentRead.model_validate(i) for i in items]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    _: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentRead:
    repo = DocumentRepository(session)
    item = await repo.get(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(item)


@router.post("/ingest", response_model=dict)
async def ingest_document(
    payload: DocumentIngestRequest,
    _: User = Depends(require_role("analyst")),
) -> dict:
    """Schedule a worker task that downloads the document and stores it on MinIO."""
    from app.services.admin_service import dispatch_ingest_document

    task_id = dispatch_ingest_document(
        record_id=payload.procurement_record_id,
        url=payload.url,
        filename=payload.filename,
    )
    return {"status": "dispatched", "task_id": task_id}
