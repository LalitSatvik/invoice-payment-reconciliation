"""Pydantic schemas for ``GET /export/summary``."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from pydantic import BaseModel


class MatchedTotals(BaseModel):
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
    unmatched: UnmatchedTotals
    exceptions_by_reason: Dict[str, ExceptionReasonTotals]
