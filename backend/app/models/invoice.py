import uuid
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

invoice_status = Enum("unmatched", "matched", "exception", name="invoice_status")


class Invoice(Base):
    """A single invoice line extracted from an upload batch."""

    __tablename__ = "invoice"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    upload_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("upload_batch.id"), nullable=False, index=True
    )
    invoice_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[date_] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date_]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'USD'")
    )
    raw_reference_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        invoice_status, nullable=False, server_default=text("'unmatched'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
