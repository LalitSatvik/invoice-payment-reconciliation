"""Persistence layer behind the upload endpoints.

Bridges Task 4's framework-free ingestion functions (``parse_csv``,
``preview_headers``, ``extract_invoice_fields``) to the ORM: creates an
``UploadBatch`` row per upload, runs the appropriate parser, persists the
rows it produced as ``Invoice``/``Payment`` records, and always leaves the
batch in a terminal ``completed``/``failed`` state describing what happened.

Both ``parse_csv`` and ``extract_invoice_fields`` canonicalize their "when"
field as a generic ``"date"`` key (invoice date for invoice-shaped parses,
payment date for bank-shaped parses) since the same CSV parser serves both
kinds of upload. The functions below are the one place that renames it to
the correct database column (``invoice_date`` / ``payment_date``) at
persistence time.

Processing is synchronous and runs inline in the request, per the MVP scale
target -- no background queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.csv_parser import RowError, parse_csv, preview_headers
from app.ingestion.pdf_extractor import extract_invoice_fields
from app.models import Invoice, Payment, SourceMapping, UploadBatch

# Row-level parse errors are summarized into UploadBatch.error_summary; this
# caps how many individual row messages get inlined so one badly-formed
# 50,000 row CSV doesn't produce a multi-megabyte error_summary.
_MAX_ROW_ERRORS_IN_SUMMARY = 20


def build_preview(csv_bytes: bytes) -> Dict[str, Any]:
    """Headers + a few sample rows for the column-mapping UI.

    ``preview_headers`` returns sample rows keyed by header name; the API's
    documented response shape is positional (one value per header, in
    header order), so this re-shapes them here.
    """
    preview = preview_headers(csv_bytes)
    headers: List[str] = preview["headers"]
    sample_rows = [
        ["" if row.get(header) is None else row[header] for header in headers]
        for row in preview["sample_rows"]
    ]
    return {"headers": headers, "sample_rows": sample_rows}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _summarize_row_errors(errors: List[RowError]) -> str:
    shown = errors[:_MAX_ROW_ERRORS_IN_SUMMARY]
    details = "; ".join(f"row {err.row_number}: {err.message}" for err in shown)
    summary = f"{len(errors)} row(s) failed to parse and were skipped: {details}"
    remaining = len(errors) - len(shown)
    if remaining > 0:
        summary += f"; ... and {remaining} more"
    return summary


def _create_processing_batch(
    db: Session, *, kind: str, filename: str, mapping_id: Optional[UUID]
) -> UploadBatch:
    """Durably persist the batch row (its own committed transaction) before
    any parsing starts, so a batch id always exists to report failure
    against -- even if parsing raises or the upload is empty.
    """
    batch = UploadBatch(
        kind=kind,
        original_filename=filename,
        status="processing",
        source_mapping_id=mapping_id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def _fail_batch(db: Session, batch: UploadBatch, message: str) -> UploadBatch:
    # Discard any rows added-but-not-committed by the caller's attempt so a
    # failed batch never leaves partial rows behind.
    db.rollback()
    batch.status = "failed"
    batch.row_count = 0
    batch.error_summary = message
    batch.completed_at = _utcnow()
    db.commit()
    db.refresh(batch)
    return batch


def _complete_batch(
    db: Session, batch: UploadBatch, row_count: int, error_summary: Optional[str]
) -> UploadBatch:
    batch.status = "completed"
    batch.row_count = row_count
    batch.error_summary = error_summary
    batch.completed_at = _utcnow()
    db.commit()
    db.refresh(batch)
    return batch


def process_invoice_csv_upload(
    db: Session, *, file_bytes: bytes, filename: str, mapping: SourceMapping
) -> UploadBatch:
    batch = _create_processing_batch(
        db, kind="invoice_csv", filename=filename, mapping_id=mapping.id
    )
    try:
        result = parse_csv(file_bytes, mapping.column_map)

        persisted = 0
        for row in result.rows:
            db.add(
                Invoice(
                    upload_batch_id=batch.id,
                    invoice_number=row.get("invoice_number"),
                    vendor_name=row.get("vendor_name"),
                    invoice_date=row["date"],
                    due_date=row.get("due_date"),
                    amount=row["amount"],
                    raw_reference_text=row.get("raw_reference_text"),
                )
            )
            persisted += 1

        if persisted == 0 and result.has_errors:
            return _fail_batch(db, batch, _summarize_row_errors(result.errors))

        error_summary = _summarize_row_errors(result.errors) if result.has_errors else None
        return _complete_batch(db, batch, persisted, error_summary)
    except Exception as exc:  # noqa: BLE001 - any parse/persist failure fails the batch, never a 500
        return _fail_batch(db, batch, str(exc))


def process_bank_csv_upload(
    db: Session, *, file_bytes: bytes, filename: str, mapping: SourceMapping
) -> UploadBatch:
    batch = _create_processing_batch(
        db, kind="bank_csv", filename=filename, mapping_id=mapping.id
    )
    try:
        result = parse_csv(file_bytes, mapping.column_map)

        persisted = 0
        for row in result.rows:
            db.add(
                Payment(
                    upload_batch_id=batch.id,
                    payment_date=row["date"],
                    amount=row["amount"],
                    reference=row.get("reference"),
                    counterparty=row.get("counterparty"),
                    raw_row=row["raw_row"],
                )
            )
            persisted += 1

        if persisted == 0 and result.has_errors:
            return _fail_batch(db, batch, _summarize_row_errors(result.errors))

        error_summary = _summarize_row_errors(result.errors) if result.has_errors else None
        return _complete_batch(db, batch, persisted, error_summary)
    except Exception as exc:  # noqa: BLE001 - any parse/persist failure fails the batch, never a 500
        return _fail_batch(db, batch, str(exc))


def process_invoice_pdf_upload(
    db: Session, *, file_bytes: bytes, filename: str
) -> UploadBatch:
    batch = _create_processing_batch(
        db, kind="invoice_pdf", filename=filename, mapping_id=None
    )
    try:
        fields = extract_invoice_fields(file_bytes)

        missing_required = [f for f in ("date", "amount") if fields.get(f) is None]
        if missing_required:
            message = (
                "could not extract required field(s) from PDF: "
                + ", ".join(missing_required)
            )
            if fields.get("warnings"):
                message += " (" + "; ".join(fields["warnings"]) + ")"
            return _fail_batch(db, batch, message)

        db.add(
            Invoice(
                upload_batch_id=batch.id,
                invoice_number=fields.get("invoice_number"),
                vendor_name=fields.get("vendor_name"),
                invoice_date=fields["date"],
                due_date=fields.get("due_date"),
                amount=fields["amount"],
            )
        )

        warnings = fields.get("warnings") or []
        error_summary = "; ".join(warnings) if warnings else None
        return _complete_batch(db, batch, 1, error_summary)
    except Exception as exc:  # noqa: BLE001 - any extraction/persist failure fails the batch, never a 500
        return _fail_batch(db, batch, str(exc))
