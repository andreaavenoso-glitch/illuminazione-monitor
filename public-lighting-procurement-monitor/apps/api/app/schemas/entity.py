from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EntityBase(BaseModel):
    name: str
    entity_type: str | None = None
    region: str | None = None
    province: str | None = None
    municipality: str | None = None
    notes: str | None = None


class EntityCreate(EntityBase):
    pass


class EntityUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    region: str | None = None
    province: str | None = None
    municipality: str | None = None
    notes: str | None = None


class EntityRead(EntityBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
