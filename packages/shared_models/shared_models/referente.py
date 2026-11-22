import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base

RUOLI = ("sindaco", "assessore", "responsabile_tecnico", "rup")


class Referente(Base):
    """A political or technical contact of an ente, with the page it was read from.
    Never inferred: the name has to be written on the cited page."""

    __tablename__ = "referenti"
    __table_args__ = (UniqueConstraint("ente", "regione", "ruolo", "nome", name="uq_referente"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ente: Mapped[str] = mapped_column(String, nullable=False, index=True)
    regione: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    ruolo: Mapped[str] = mapped_column(String, nullable=False)  # see RUOLI
    qualifica: Mapped[str | None] = mapped_column(String, nullable=True)  # as written: "Assessore ai LL.PP."
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String, nullable=True)
    fonte_url: Mapped[str] = mapped_column(String, nullable=False)
    citazione: Mapped[str | None] = mapped_column(Text, nullable=True)
    # verificato: name and role read together on the cited page; da_confermare: name found
    # on the page but the role is not next to it.
    stato: Mapped[str] = mapped_column(String, nullable=False, default="da_confermare")
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
