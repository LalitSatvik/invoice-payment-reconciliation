"""Persistence layer behind the matching, match-review, and exception-review
endpoints.

Bridges Task 5's framework-free ``app.matching`` package to the ORM: loads
currently-unmatched ``Invoice``/``Payment`` rows into the engine's plain
dataclasses, runs ``run_matching``, and persists the resulting ``Match``/
``ExceptionRecord`` rows -- flipping ``invoice.status``/``payment.status``
to reflect the outcome. Also implements the reviewer-facing state
transitions (accept/reject a match, resolve an exception).

``InvoiceRecord.id``/``PaymentRecord.id`` are strings (the engine is
framework-free and knows nothing about UUIDs); every boundary in this module
converts UUID primary keys to ``str`` going in and back to ``UUID`` going
out.

``ExceptionRecord.candidate_ids`` (JSONB) is stored as a list of
``{"id": <record_id str>, "confidence": <float>}`` objects, one per
``CandidateRef`` the engine returned, best-first -- the same shape as
``CandidateRef`` itself, so no information the engine computed is discarded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.matching import DEFAULT_CONFIG, SIDE_INVOICE, InvoiceRecord, PaymentRecord, run_matching
from app.matching.types import ScoredMatch
from app.models import ExceptionRecord, Invoice, Match, Payment
from app.models.exception import exception_reason, exception_status
from app.models.match import match_status_type

REASON_REJECTED_BY_REVIEWER = "rejected_by_reviewer"

VALID_MATCH_STATUSES = frozenset(match_status_type.enums)
VALID_EXCEPTION_STATUSES = frozenset(exception_status.enums)
VALID_EXCEPTION_REASONS = frozenset(exception_reason.enums)

# Manual overrides (POST /exceptions/{id}/resolve, link mode) bypass scoring
# entirely, so there is no engine-computed confidence to store. A full-marks
# score communicates "a human vouched for this pairing directly" rather than
# implying the scoring algorithm produced this value.
MANUAL_OVERRIDE_SCORE = Decimal("100.00")


class MatchNotFoundError(Exception):
    """Raised when a match id does not exist."""


class MatchAlreadyReviewedError(Exception):
    """Raised when accept/reject is attempted on a non-``suggested`` match."""


class ExceptionNotFoundError(Exception):
    """Raised when an exception id does not exist."""


class ExceptionAlreadyResolvedError(Exception):
    """Raised when resolve is attempted on an already-resolved exception."""


class InvalidResolutionError(Exception):
    """Raised when a resolve request's link ids are invalid or unusable."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _score_to_decimal(value: float) -> Decimal:
    """Engine sub-scores are Python floats on a 0-100 scale; the ``Match``
    columns are ``Numeric(5, 2)``. Round via ``Decimal(str(...))`` rather
    than ``Decimal(value)`` to avoid pulling in a float's binary-fraction
    noise (e.g. 66.24999999999999) ahead of the rounding step.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_invoice_record(invoice: Invoice) -> InvoiceRecord:
    return InvoiceRecord(
        id=str(invoice.id),
        amount=invoice.amount,
        date=invoice.invoice_date,
        invoice_number=invoice.invoice_number,
        vendor_name=invoice.vendor_name,
        raw_reference_text=invoice.raw_reference_text,
        due_date=invoice.due_date,
    )


def _to_payment_record(payment: Payment) -> PaymentRecord:
    return PaymentRecord(
        id=str(payment.id),
        amount=payment.amount,
        date=payment.payment_date,
        reference=payment.reference,
        counterparty=payment.counterparty,
    )


def _candidate_ids_json(candidates) -> List[Dict[str, Any]]:
    return [{"id": c.record_id, "confidence": c.confidence} for c in candidates]


def run_matching_for_unmatched(
    db: Session, *, batch_ids: Optional[Sequence[UUID]] = None
) -> Dict[str, int]:
    """Load all currently-``unmatched`` invoices/payments (optionally scoped
    to ``batch_ids``), run the matching engine, and persist the outcome.

    Every ``ScoredMatch`` becomes a ``Match`` row with ``match_status=
    suggested``, and both linked records flip to ``status=matched`` -- there
    is no "pending review" state in the ``invoice_status``/``payment_status``
    enums, so a suggested-but-unreviewed match still has to leave the
    "unmatched" pool (otherwise a second run would try to match the same
    records again). ``reject`` reopens both sides back to ``unmatched`` so a
    future run (or manual resolution) can reconsider them.

    Every ``ExceptionCandidate`` becomes an ``ExceptionRecord`` row with
    ``status=open``, and the one side it names flips to ``status=exception``.
    """
    invoice_query = db.query(Invoice).filter(Invoice.status == "unmatched")
    payment_query = db.query(Payment).filter(Payment.status == "unmatched")
    if batch_ids:
        invoice_query = invoice_query.filter(Invoice.upload_batch_id.in_(batch_ids))
        payment_query = payment_query.filter(Payment.upload_batch_id.in_(batch_ids))

    invoices = invoice_query.all()
    payments = payment_query.all()

    invoices_by_id = {str(inv.id): inv for inv in invoices}
    payments_by_id = {str(pay.id): pay for pay in payments}

    result = run_matching(
        [_to_invoice_record(inv) for inv in invoices],
        [_to_payment_record(pay) for pay in payments],
        DEFAULT_CONFIG,
    )

    matches_created = 0
    for scored in result.matches:  # type: ScoredMatch
        invoice = invoices_by_id[scored.invoice_id]
        payment = payments_by_id[scored.payment_id]
        db.add(
            Match(
                invoice_id=invoice.id,
                payment_id=payment.id,
                confidence_score=_score_to_decimal(scored.confidence),
                amount_score=_score_to_decimal(scored.amount_score),
                date_score=_score_to_decimal(scored.date_score),
                reference_score=_score_to_decimal(scored.reference_score),
                match_status="suggested",
            )
        )
        invoice.status = "matched"
        payment.status = "matched"
        matches_created += 1

    exceptions_created = 0
    for candidate in result.exceptions:
        candidate_ids = _candidate_ids_json(candidate.candidates)
        if candidate.side == SIDE_INVOICE:
            invoice = invoices_by_id[candidate.record_id]
            invoice.status = "exception"
            db.add(
                ExceptionRecord(
                    invoice_id=invoice.id,
                    payment_id=None,
                    reason=candidate.reason,
                    candidate_ids=candidate_ids,
                    status="open",
                )
            )
        else:
            payment = payments_by_id[candidate.record_id]
            payment.status = "exception"
            db.add(
                ExceptionRecord(
                    invoice_id=None,
                    payment_id=payment.id,
                    reason=candidate.reason,
                    candidate_ids=candidate_ids,
                    status="open",
                )
            )
        exceptions_created += 1

    db.commit()
    return {"matches_created": matches_created, "exceptions_created": exceptions_created}


def list_matches(
    db: Session,
    *,
    status: Optional[str] = None,
    min_confidence: Optional[Decimal] = None,
    max_confidence: Optional[Decimal] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Match], int]:
    query = db.query(Match)
    if status is not None:
        query = query.filter(Match.match_status == status)
    if min_confidence is not None:
        query = query.filter(Match.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.filter(Match.confidence_score <= max_confidence)

    total = query.count()
    items = (
        query.order_by(Match.suggested_at.desc(), Match.id).offset(offset).limit(limit).all()
    )
    return items, total


def get_match_detail(
    db: Session, match_id: UUID
) -> Optional[Tuple[Match, Invoice, Payment]]:
    """The match plus both linked records, for the side-by-side review card.

    ``Match`` carries no ORM relationships to ``Invoice``/``Payment`` (Task 2
    modeled them as plain foreign-key columns), so the two related rows are
    fetched alongside it here rather than via attribute access.
    """
    match = db.get(Match, match_id)
    if match is None:
        return None
    invoice = db.get(Invoice, match.invoice_id)
    payment = db.get(Payment, match.payment_id)
    return match, invoice, payment


def accept_match(db: Session, match_id: UUID) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise MatchNotFoundError(f"match {match_id} not found")
    if match.match_status != "suggested":
        raise MatchAlreadyReviewedError(
            f"match {match_id} has already been reviewed (match_status={match.match_status!r})"
        )

    match.match_status = "accepted"
    match.reviewed_at = _utcnow()

    invoice = db.get(Invoice, match.invoice_id)
    payment = db.get(Payment, match.payment_id)
    invoice.status = "matched"
    payment.status = "matched"

    db.commit()
    db.refresh(match)
    return match


def reject_match(db: Session, match_id: UUID) -> Dict[str, Any]:
    """Reject a suggested match and reopen both sides for future matching.

    The ``Match`` row is deleted rather than kept around with
    ``match_status="rejected"``: ``invoice_id``/``payment_id`` each carry a
    table-wide unique constraint (not scoped to non-rejected rows), so a
    rejected row left in place would permanently block that exact invoice or
    payment from ever appearing in a new ``Match`` row again -- including the
    very next ``/matching/run``, which (nothing else about the data having
    changed) immediately re-proposes the same pairing and collides with the
    stale row on both columns at once. The durable record of "this pairing
    was proposed and rejected" is the ``ExceptionRecord`` created below, not
    the ``Match`` row, so deleting it costs no audit-trail information -- it
    does mean ``match_status="rejected"`` is no longer a state any row is
    ever found in; ``GET /matches?status=rejected`` will simply always come
    back empty. See the ``rejected`` value's note on ``match_status_type``.
    """
    match = db.get(Match, match_id)
    if match is None:
        raise MatchNotFoundError(f"match {match_id} not found")
    if match.match_status != "suggested":
        raise MatchAlreadyReviewedError(
            f"match {match_id} has already been reviewed (match_status={match.match_status!r})"
        )

    invoice = db.get(Invoice, match.invoice_id)
    payment = db.get(Payment, match.payment_id)
    invoice.status = "unmatched"
    payment.status = "unmatched"

    db.add(
        ExceptionRecord(
            invoice_id=invoice.id,
            payment_id=payment.id,
            reason=REASON_REJECTED_BY_REVIEWER,
            candidate_ids=None,
            status="open",
        )
    )

    # Build the response payload before deleting -- SQLAlchemy expires a
    # deleted instance's attributes on flush/commit, and the caller still
    # needs to render this match's final state (id, rejected timestamp, etc.)
    # in the response. A plain dict is returned rather than the (now
    # deleted) ORM instance; ``MatchOut`` validates it the same way either
    # form arrives.
    response = {
        "id": match.id,
        "invoice_id": match.invoice_id,
        "payment_id": match.payment_id,
        "confidence_score": match.confidence_score,
        "amount_score": match.amount_score,
        "date_score": match.date_score,
        "reference_score": match.reference_score,
        "match_status": "rejected",
        "suggested_at": match.suggested_at,
        "reviewed_at": _utcnow(),
        "reviewer_note": match.reviewer_note,
    }

    db.delete(match)
    db.commit()
    return response


def list_exceptions(
    db: Session,
    *,
    status: Optional[str] = None,
    reason: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ExceptionRecord], int]:
    query = db.query(ExceptionRecord)
    if status is not None:
        query = query.filter(ExceptionRecord.status == status)
    if reason is not None:
        query = query.filter(ExceptionRecord.reason == reason)

    total = query.count()
    items = (
        query.order_by(ExceptionRecord.created_at.desc(), ExceptionRecord.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def resolve_exception(
    db: Session,
    exception_id: UUID,
    *,
    link_invoice_id: Optional[UUID] = None,
    link_payment_id: Optional[UUID] = None,
    dismiss: bool = False,
    resolution_note: Optional[str] = None,
) -> ExceptionRecord:
    record = db.get(ExceptionRecord, exception_id)
    if record is None:
        raise ExceptionNotFoundError(f"exception {exception_id} not found")
    if record.status != "open":
        raise ExceptionAlreadyResolvedError(
            f"exception {exception_id} has already been resolved (status={record.status!r})"
        )

    if dismiss:
        record.status = "resolved"
        record.resolution_note = resolution_note
        record.resolved_at = _utcnow()
        db.commit()
        db.refresh(record)
        return record

    invoice = db.get(Invoice, link_invoice_id)
    if invoice is None:
        raise InvalidResolutionError(f"invoice {link_invoice_id} not found")
    payment = db.get(Payment, link_payment_id)
    if payment is None:
        raise InvalidResolutionError(f"payment {link_payment_id} not found")

    existing_for_invoice = (
        db.query(Match).filter(Match.invoice_id == invoice.id).first()
    )
    if existing_for_invoice is not None:
        raise InvalidResolutionError(
            f"invoice {link_invoice_id} is already linked to match {existing_for_invoice.id}"
        )
    existing_for_payment = (
        db.query(Match).filter(Match.payment_id == payment.id).first()
    )
    if existing_for_payment is not None:
        raise InvalidResolutionError(
            f"payment {link_payment_id} is already linked to match {existing_for_payment.id}"
        )

    match = Match(
        invoice_id=invoice.id,
        payment_id=payment.id,
        confidence_score=MANUAL_OVERRIDE_SCORE,
        amount_score=MANUAL_OVERRIDE_SCORE,
        date_score=MANUAL_OVERRIDE_SCORE,
        reference_score=MANUAL_OVERRIDE_SCORE,
        match_status="accepted",
        reviewed_at=_utcnow(),
        reviewer_note=f"manual resolution of exception {exception_id}",
    )
    db.add(match)

    invoice.status = "matched"
    payment.status = "matched"

    record.status = "resolved"
    record.resolution_note = resolution_note
    record.resolved_at = _utcnow()

    db.commit()
    db.refresh(record)
    return record
