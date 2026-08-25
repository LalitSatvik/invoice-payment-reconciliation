"""Endpoints for running the matching engine and reviewing its suggestions."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.match import (
    MatchDetailOut,
    MatchingRunRequest,
    MatchingRunResponse,
    MatchListResponse,
    MatchOut,
)
from app.services import matching_service

router = APIRouter(tags=["matches"])


@router.post("/matching/run", response_model=MatchingRunResponse)
def run_matching(
    payload: MatchingRunRequest = Body(default_factory=MatchingRunRequest),
    db: Session = Depends(get_db),
) -> dict:
    """Match all currently-unmatched invoices/payments (optionally scoped to
    ``batch_ids``) and persist the outcome.
    """
    return matching_service.run_matching_for_unmatched(db, batch_ids=payload.batch_ids)


@router.get("/matches", response_model=MatchListResponse)
def list_matches(
    status: Optional[str] = Query(None),
    min_confidence: Optional[Decimal] = Query(None),
    max_confidence: Optional[Decimal] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    if status is not None and status not in matching_service.VALID_MATCH_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(matching_service.VALID_MATCH_STATUSES)}",
        )

    items, total = matching_service.list_matches(
        db,
        status=status,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/matches/{match_id}", response_model=MatchDetailOut)
def get_match(match_id: uuid.UUID, db: Session = Depends(get_db)):
    result = matching_service.get_match_detail(db, match_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    match, invoice, payment = result
    return {
        "id": match.id,
        "invoice_id": match.invoice_id,
        "payment_id": match.payment_id,
        "confidence_score": match.confidence_score,
        "amount_score": match.amount_score,
        "date_score": match.date_score,
        "reference_score": match.reference_score,
        "match_status": match.match_status,
        "suggested_at": match.suggested_at,
        "reviewed_at": match.reviewed_at,
        "reviewer_note": match.reviewer_note,
        "invoice": invoice,
        "payment": payment,
    }


@router.post("/matches/{match_id}/accept", response_model=MatchOut)
def accept_match(match_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return matching_service.accept_match(db, match_id)
    except matching_service.MatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except matching_service.MatchAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/matches/{match_id}/reject", response_model=MatchOut)
def reject_match(match_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return matching_service.reject_match(db, match_id)
    except matching_service.MatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except matching_service.MatchAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
