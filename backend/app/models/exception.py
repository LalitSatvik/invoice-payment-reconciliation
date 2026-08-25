import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

exception_reason = Enum(
    "no_candidate",
    "ambiguous_multiple_candidates",
    "below_threshold",
    "possible_split_payment",
    "rejected_by_reviewer",
    "amount_mismatch_only",
    name="exception_reason",
)
exception_status = Enum("open", "resolved", name="exception_status")


class ExceptionRecord(Base):
    """An unresolved (or resolved) reconciliation issue for review.

    Named ``ExceptionRecord`` rather than ``Exception`` to avoid shadowing the
    builtin; the table itself is named ``exception`` per the schema spec.
    """

    __tablename__ = "exception"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice.id"), nullable=True, index=True
    )
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(exception_reason, nullable=False)
    candidate_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        exception_status, nullable=False, server_default=text("'open'")
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
