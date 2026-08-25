"""Plain data structures used by the matching engine.

This module (and the rest of ``app.matching``) is deliberately framework-free:
no SQLAlchemy, no FastAPI, no imports from ``app.db`` or ``app.api``. The engine
operates on simple dataclasses so it can be unit-tested in isolation and reused
from any caller (API handler, CLI, batch job, test harness).
"""

from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal
from typing import List, Optional

# Exception reasons emitted by the engine for records that do not commit to a
# match. These strings are the engine's own vocabulary and are what downstream
# persistence should store.
REASON_NO_CANDIDATE = "no_candidate"
REASON_BELOW_THRESHOLD = "below_threshold"
REASON_AMBIGUOUS = "ambiguous_multiple_candidates"
REASON_CANDIDATE_CLAIMED = "candidate_claimed_elsewhere"

SIDE_INVOICE = "invoice"
SIDE_PAYMENT = "payment"


@dataclass(frozen=True)
class InvoiceRecord:
    """One invoice, normalized for matching.

    ``date`` is the invoice date. ``due_date`` is the date the invoice falls
    due; when present it is the anchor the date-tolerance window is measured
    from, because payments are made relative to the due date, not to the date
    the invoice was raised.
    """

    id: str
    amount: Decimal
    date: date_type
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    raw_reference_text: Optional[str] = None
    due_date: Optional[date_type] = None

    @property
    def date_anchor(self) -> date_type:
        """The invoice date the payment date is compared against."""
        return self.due_date if self.due_date is not None else self.date


@dataclass(frozen=True)
class PaymentRecord:
    """One bank transaction, normalized for matching."""

    id: str
    amount: Decimal
    date: date_type
    reference: Optional[str] = None
    counterparty: Optional[str] = None


@dataclass(frozen=True)
class ScoredMatch:
    """A single invoice/payment pair with its explainable sub-scores."""

    invoice_id: str
    payment_id: str
    amount_score: float
    date_score: float
    reference_score: float
    confidence: float


@dataclass(frozen=True)
class CandidateRef:
    """A pointer to a competing candidate, carried on an exception."""

    record_id: str
    confidence: float


@dataclass(frozen=True)
class ExceptionCandidate:
    """A record that did not commit to a match, and why.

    ``side`` is which list the unmatched record came from, ``record_id`` is its
    id, ``reason`` is one of the ``REASON_*`` constants, and ``candidates``
    lists the records on the *opposite* side that were in play, best first.
    """

    side: str
    record_id: str
    reason: str
    candidates: List[CandidateRef] = field(default_factory=list)


@dataclass(frozen=True)
class MatchingResult:
    """The full outcome of a matching run."""

    matches: List[ScoredMatch] = field(default_factory=list)
    exceptions: List[ExceptionCandidate] = field(default_factory=list)
