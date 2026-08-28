"""Pydantic schemas for ``GET /export/summary``."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from pydantic import BaseModel


class MatchedTotals(BaseModel):
    """Count + invoice-side dollar total for one match bucket (``matched``
    for accepted matches, ``in_review`` for suggested-but-unreviewed ones)."""

    count: int
    amount: Decimal


class UnmatchedSideTotals(BaseModel):
    count: int
    amount: Decimal


class UnmatchedTotals(BaseModel):
    invoices: UnmatchedSideTotals
    payments: UnmatchedSideTotals


class ExceptionReasonTotals(BaseModel):
    count: int
    amount: Optional[Decimal] = None


class ExportSummaryResponse(BaseModel):
    generated_at: datetime
    matched: MatchedTotals
    #: Matches the engine has suggested that nobody has accepted or rejected
    #: yet. These records are already out of the ``unmatched`` pool, so
    #: without this bucket they appear in no total at all.
    in_review: MatchedTotals
    unmatched: UnmatchedTotals
    exceptions_by_reason: Dict[str, ExceptionReasonTotals]
