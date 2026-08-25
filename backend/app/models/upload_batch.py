import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

upload_batch_kind = Enum(
    "invoice_pdf", "invoice_csv", "bank_csv", name="upload_batch_kind"
)
upload_batch_status = Enum(
    "pending", "processing", "completed", "failed", name="upload_batch_status"
)


class UploadBatch(Base):
    """A single file upload (invoices or bank payments) submitted for processing."""

    __tablename__ = "upload_batch"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(upload_batch_kind, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(upload_batch_status, nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_mapping_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_mapping.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
