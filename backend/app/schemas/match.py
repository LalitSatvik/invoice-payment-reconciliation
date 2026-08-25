"""Pydantic schemas for the matching-run and match review API."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class MatchingRunRequest(BaseModel):
    """Body for ``POST /matching/run``.

    ``batch_ids`` optionally scopes the run to invoices/payments from these
    upload batches only; omitted or empty means "all currently unmatched
    invoices and payments, regardless of batch".
    """

    batch_ids: Optional[List[uuid.UUID]] = None


class MatchingRunResponse(BaseModel):
    matches_created: int
    exceptions_created: int


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    upload_batch_id: uuid.UUID
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: date
    due_date: Optional[date] = None
    amount: Decimal
    currency: str
    raw_reference_text: Optional[str] = None
    status: str


class PaymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    upload_batch_id: uuid.UUID
    payment_date: date
    amount: Decimal
    currency: str
    reference: Optional[str] = None
    counterparty: Optional[str] = None
    status: str


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    payment_id: uuid.UUID
    confidence_score: Decimal
    amount_score: Decimal
    date_score: Decimal
    reference_score: Decimal
    match_status: str
    suggested_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewer_note: Optional[str] = None


class MatchDetailOut(MatchOut):
    """Full detail for the side-by-side review card."""

    invoice: InvoiceSummary
    payment: PaymentSummary


class MatchListResponse(BaseModel):
    items: List[MatchOut]
    total: int
    limit: int
    offset: int
