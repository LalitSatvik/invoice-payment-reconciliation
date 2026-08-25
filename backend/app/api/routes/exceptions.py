"""Endpoints for listing and resolving reconciliation exceptions."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.exception import ExceptionListResponse, ExceptionOut, ExceptionResolveRequest
from app.services import matching_service

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=ExceptionListResponse)
def list_exceptions(
    status: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    if status is not None and status not in matching_service.VALID_EXCEPTION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(matching_service.VALID_EXCEPTION_STATUSES)}",
        )
    if reason is not None and reason not in matching_service.VALID_EXCEPTION_REASONS:
        raise HTTPException(
            status_code=422,
            detail=f"reason must be one of {sorted(matching_service.VALID_EXCEPTION_REASONS)}",
        )

    items, total = matching_service.list_exceptions(
        db, status=status, reason=reason, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/{exception_id}/resolve", response_model=ExceptionOut)
def resolve_exception(
    exception_id: uuid.UUID,
    payload: ExceptionResolveRequest,
    db: Session = Depends(get_db),
):
    try:
        return matching_service.resolve_exception(
            db,
            exception_id,
            link_invoice_id=payload.link_invoice_id,
            link_payment_id=payload.link_payment_id,
            dismiss=payload.dismiss,
            resolution_note=payload.resolution_note,
        )
    except matching_service.ExceptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except matching_service.ExceptionAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except matching_service.InvalidResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
