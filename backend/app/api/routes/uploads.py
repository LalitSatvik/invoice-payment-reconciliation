"""Upload endpoints: CSV preview, invoice ingestion (PDF or CSV), bank
statement ingestion, and batch status lookup.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SourceMapping, UploadBatch
from app.schemas.upload import PreviewResponse, UploadBatchOut
from app.services import upload_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _looks_like_pdf(filename: str, content_type: Optional[str]) -> bool:
    if content_type == "application/pdf":
        return True
    return filename.lower().endswith(".pdf")


@router.post("/preview", response_model=PreviewResponse)
def preview_upload(file: UploadFile = File(...)) -> dict:
    """Parse headers + a few sample rows only -- no persistence. Drives the
    frontend's column-mapping step before a mapping is chosen/saved.
    """
    contents = file.file.read()
    try:
        return upload_service.build_preview(contents)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/invoices", response_model=UploadBatchOut, status_code=201)
def upload_invoices(
    file: UploadFile = File(...),
    source_mapping_id: Optional[uuid.UUID] = Form(None),
    db: Session = Depends(get_db),
) -> UploadBatch:
    """Ingest an invoice file: PDF (heuristic extraction, no mapping needed)
    or CSV (mapping-driven, ``source_mapping_id`` required).
    """
    filename = file.filename or "upload"
    contents = file.file.read()

    if _looks_like_pdf(filename, file.content_type):
        return upload_service.process_invoice_pdf_upload(
            db, file_bytes=contents, filename=filename
        )

    if source_mapping_id is None:
        raise HTTPException(
            status_code=422,
            detail="source_mapping_id is required for CSV invoice uploads",
        )
    mapping = db.get(SourceMapping, source_mapping_id)
    if mapping is None:
        raise HTTPException(
            status_code=404, detail=f"source mapping {source_mapping_id} not found"
        )
    if mapping.target_kind != "invoice":
        raise HTTPException(
            status_code=422,
            detail=f"source mapping {source_mapping_id} is not an invoice mapping",
        )

    return upload_service.process_invoice_csv_upload(
        db, file_bytes=contents, filename=filename, mapping=mapping
    )


@router.post("/bank-statement", response_model=UploadBatchOut, status_code=201)
def upload_bank_statement(
    file: UploadFile = File(...),
    source_mapping_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
) -> UploadBatch:
    """Ingest a bank statement CSV; ``source_mapping_id`` is always required."""
    filename = file.filename or "upload"
    contents = file.file.read()

    mapping = db.get(SourceMapping, source_mapping_id)
    if mapping is None:
        raise HTTPException(
            status_code=404, detail=f"source mapping {source_mapping_id} not found"
        )
    if mapping.target_kind != "payment":
        raise HTTPException(
            status_code=422,
            detail=f"source mapping {source_mapping_id} is not a payment mapping",
        )

    return upload_service.process_bank_csv_upload(
        db, file_bytes=contents, filename=filename, mapping=mapping
    )


@router.get("/{batch_id}", response_model=UploadBatchOut)
def get_upload_batch(batch_id: uuid.UUID, db: Session = Depends(get_db)) -> UploadBatch:
    batch = db.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"upload batch {batch_id} not found")
    return batch
