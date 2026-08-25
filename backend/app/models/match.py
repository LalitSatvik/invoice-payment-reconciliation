import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

match_status_type = Enum("suggested", "accepted", "rejected", name="match_status")
# Note (Task 7): rejecting a match deletes its ``Match`` row rather than
# setting match_status="rejected" and leaving it -- the row's invoice_id/
# payment_id unique constraints would otherwise permanently block that
# invoice or payment from ever being matched again, including on the very
# next matching run. The audit trail for a rejection lives on an
# ExceptionRecord(reason="rejected_by_reviewer") instead. The "rejected"
# enum value is kept (no migration needed to remove it) but no row is
# ever expected to be found in that state; see
# app.services.matching_service.reject_match.


class Match(Base):
    """A 1:1 pairing between an invoice and a payment, suggested or confirmed."""

    __tablename__ = "match"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice.id"), nullable=False, unique=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id"), nullable=False, unique=True
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    amount_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    date_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reference_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    match_status: Mapped[str] = mapped_column(match_status_type, nullable=False)
    suggested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
