"""Framework-free invoice-to-payment matching engine.

Contains no imports from ``app.db``, ``app.api``, SQLAlchemy or FastAPI: the
scoring rules and the commitment algorithm are pure functions over plain
dataclasses, so they can be tested and reasoned about on their own.
"""

from app.matching.config import DEFAULT_CONFIG, MatchConfig
from app.matching.engine import generate_candidates, run_matching
from app.matching.scoring import (
    score_amount,
    score_date,
    score_pair,
    score_reference,
)
from app.matching.types import (
    REASON_AMBIGUOUS,
    REASON_BELOW_THRESHOLD,
    REASON_CANDIDATE_CLAIMED,
    REASON_NO_CANDIDATE,
    SIDE_INVOICE,
    SIDE_PAYMENT,
    CandidateRef,
    ExceptionCandidate,
    InvoiceRecord,
    MatchingResult,
    PaymentRecord,
    ScoredMatch,
)

__all__ = [
    "DEFAULT_CONFIG",
    "MatchConfig",
    "InvoiceRecord",
    "PaymentRecord",
    "ScoredMatch",
    "CandidateRef",
    "ExceptionCandidate",
    "MatchingResult",
    "REASON_NO_CANDIDATE",
    "REASON_BELOW_THRESHOLD",
    "REASON_AMBIGUOUS",
    "REASON_CANDIDATE_CLAIMED",
    "SIDE_INVOICE",
    "SIDE_PAYMENT",
    "score_amount",
    "score_date",
    "score_reference",
    "score_pair",
    "generate_candidates",
    "run_matching",
]
