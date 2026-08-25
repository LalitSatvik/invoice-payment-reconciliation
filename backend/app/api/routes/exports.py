"""Endpoints producing the reconciliation exports."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.export import ExportSummaryResponse
from app.services import export_service

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/reconciliation.csv")
def export_reconciliation_csv(db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream a CSV, one row per accepted match."""
    return StreamingResponse(
        export_service.stream_reconciliation_csv(db),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=reconciliation.csv",
        },
    )


@router.get("/summary", response_model=ExportSummaryResponse)
def export_summary(db: Session = Depends(get_db)) -> dict:
    return export_service.get_export_summary(db)
