import uuid
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

payment_status = Enum("unmatched", "matched", "exception", name="payment_status")


class Payment(Base):
    """A single payment/transaction row extracted from a bank CSV upload batch."""

    __tablename__ = "payment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    upload_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("upload_batch.id"), nullable=False, index=True
    )
    payment_date: Mapped[date_] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'USD'")
    )
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counterparty: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        payment_status, nullable=False, server_default=text("'unmatched'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
