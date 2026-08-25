import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

source_mapping_target_kind = Enum("invoice", "payment", name="source_mapping_target_kind")


class SourceMapping(Base):
    """A saved column mapping for a recurring CSV source (e.g. a specific bank export)."""

    __tablename__ = "source_mapping"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    target_kind: Mapped[str] = mapped_column(source_mapping_target_kind, nullable=False)
    column_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )
