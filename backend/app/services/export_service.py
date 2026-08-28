"""Read-side queries behind the reconciliation exports.

``build_reconciliation_csv_rows`` and ``get_export_summary`` are pure
read/aggregate operations over ``Invoice``/``Payment``/``Match``/
``ExceptionRecord`` -- nothing here mutates state.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterator, List

from sqlalchemy.orm import Session

from app.models import ExceptionRecord, Invoice, Match, Payment

# Column order for GET /export/reconciliation.csv, one row per *accepted*
# match. Amount/date variance are computed relative to the invoice side
# (payment minus invoice, and payment date minus invoice date) since the
# invoice is the "expected" record the payment is reconciled against.
CSV_FIELDNAMES = [
    "match_id",
    "invoice_id",
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "invoice_due_date",
    "invoice_amount",
    "payment_id",
    "payment_date",
    "payment_reference",
    "payment_counterparty",
    "payment_amount",
    "amount_variance",
    "date_variance_days",
    "confidence_score",
    "amount_score",
    "date_score",
    "reference_score",
    "reviewed_at",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _accepted_matches_with_records(db: Session):
    """Accepted matches, oldest-reviewed-first, each paired with its invoice
    and payment. A match's linked invoice/payment always exist (foreign
    keys are non-nullable and nothing deletes them), so no None-guarding is
    needed here.
    """
    rows = (
        db.query(Match, Invoice, Payment)
        .join(Invoice, Match.invoice_id == Invoice.id)
        .join(Payment, Match.payment_id == Payment.id)
        .filter(Match.match_status == "accepted")
        .order_by(Match.reviewed_at, Match.id)
        .all()
    )
    return rows


def _csv_row(match: Match, invoice: Invoice, payment: Payment) -> Dict[str, Any]:
    amount_variance = payment.amount - invoice.amount
    date_variance_days = (payment.payment_date - invoice.invoice_date).days
    return {
        "match_id": str(match.id),
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number or "",
        "vendor_name": invoice.vendor_name or "",
        "invoice_date": invoice.invoice_date.isoformat(),
        "invoice_due_date": invoice.due_date.isoformat() if invoice.due_date else "",
        "invoice_amount": str(invoice.amount),
        "payment_id": str(payment.id),
        "payment_date": payment.payment_date.isoformat(),
        "payment_reference": payment.reference or "",
        "payment_counterparty": payment.counterparty or "",
        "payment_amount": str(payment.amount),
        "amount_variance": str(amount_variance),
        "date_variance_days": date_variance_days,
        "confidence_score": str(match.confidence_score),
        "amount_score": str(match.amount_score),
        "date_score": str(match.date_score),
        "reference_score": str(match.reference_score),
        "reviewed_at": match.reviewed_at.isoformat() if match.reviewed_at else "",
    }


def stream_reconciliation_csv(db: Session) -> Iterator[str]:
    """Yield the reconciliation CSV one line at a time, header first, so the
    route can hand it to a ``StreamingResponse`` without buffering the whole
    file in memory.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)

    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for match, invoice, payment in _accepted_matches_with_records(db):
        writer.writerow(_csv_row(match, invoice, payment))
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def _zero() -> Decimal:
    return Decimal("0.00")


def _match_totals(db: Session, match_status: str) -> Dict[str, Any]:
    rows = (
        db.query(Match, Invoice)
        .join(Invoice, Match.invoice_id == Invoice.id)
        .filter(Match.match_status == match_status)
        .all()
    )
    return {
        "count": len(rows),
        "amount": sum((invoice.amount for _, invoice in rows), _zero()),
    }


def get_export_summary(db: Session) -> Dict[str, Any]:
    """Totals matched/in-review/unmatched (count + $) and *open* exceptions
    grouped by reason (count + $), as of right now.

    ``matched`` counts accepted matches only; ``in_review`` counts matches the
    engine has suggested but nobody has accepted or rejected yet. Both buckets
    are needed because ``run_matching_for_unmatched`` flips both linked
    records to ``status="matched"`` the moment a match is *suggested* -- so a
    suggested-but-unreviewed record is in neither the accepted-match pool nor
    the unmatched pool, and reporting only ``matched``/``unmatched`` would
    make it vanish from the summary entirely.

    Matched ``$`` is the invoice-side amount (the two sides agree within
    the matching engine's amount tolerance by construction, so either side
    would do; invoice amount is the "billed" figure). Unmatched invoice-side
    and payment-side totals are reported separately per the spec, since an
    unmatched invoice's amount and an unmatched payment's amount are not
    interchangeable. Exception amounts use whichever side the exception
    record names (invoice amount if ``invoice_id`` is set, else payment
    amount) -- a ``rejected_by_reviewer`` exception, the one kind linked to
    both sides, is counted once via its invoice amount to avoid
    double-counting the same reconciliation event.

    ``exceptions_by_reason`` aggregates ``status="open"`` rows only: it is a
    measure of outstanding review work, and counting resolved rows too made
    it a monotonically growing tally that never went down as reviewers
    cleared the queue.
    """
    matched = _match_totals(db, "accepted")
    in_review = _match_totals(db, "suggested")

    unmatched_invoices = db.query(Invoice).filter(Invoice.status == "unmatched").all()
    unmatched_invoice_count = len(unmatched_invoices)
    unmatched_invoice_amount = sum((inv.amount for inv in unmatched_invoices), _zero())

    unmatched_payments = db.query(Payment).filter(Payment.status == "unmatched").all()
    unmatched_payment_count = len(unmatched_payments)
    unmatched_payment_amount = sum((pay.amount for pay in unmatched_payments), _zero())

    exceptions_by_reason: Dict[str, Dict[str, Any]] = {}
    open_exceptions = (
        db.query(ExceptionRecord).filter(ExceptionRecord.status == "open").all()
    )
    for record in open_exceptions:
        bucket = exceptions_by_reason.setdefault(
            record.reason, {"count": 0, "amount": _zero()}
        )
        bucket["count"] += 1

        amount = None
        if record.invoice_id is not None:
            invoice = db.get(Invoice, record.invoice_id)
            if invoice is not None:
                amount = invoice.amount
        elif record.payment_id is not None:
            payment = db.get(Payment, record.payment_id)
            if payment is not None:
                amount = payment.amount
        if amount is not None:
            bucket["amount"] += amount

    return {
        "generated_at": _utcnow(),
        "matched": matched,
        "in_review": in_review,
        "unmatched": {
            "invoices": {
                "count": unmatched_invoice_count,
                "amount": unmatched_invoice_amount,
            },
            "payments": {
                "count": unmatched_payment_count,
                "amount": unmatched_payment_amount,
            },
        },
        "exceptions_by_reason": exceptions_by_reason,
    }
