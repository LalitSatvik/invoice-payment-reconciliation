"""Pydantic schemas for the exception review API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class ExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: Optional[uuid.UUID] = None
    payment_id: Optional[uuid.UUID] = None
    reason: str
    candidate_ids: Optional[List[Dict[str, Any]]] = None
    status: str
    resolution_note: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ExceptionListResponse(BaseModel):
    items: List[ExceptionOut]
    total: int
    limit: int
    offset: int


class ExceptionResolveRequest(BaseModel):
    """Body for ``POST /exceptions/{id}/resolve``.

    Exactly one of the two resolution modes must be used:
    - link mode: both ``link_invoice_id`` and ``link_payment_id`` set, creates
      a ``Match`` directly with ``match_status=accepted`` (a manual override
      that bypasses scoring entirely).
    - dismiss mode: ``dismiss=True``, marks the exception ``status=resolved``
      with no match created. ``resolution_note`` is accepted in either mode.
    """

    link_invoice_id: Optional[uuid.UUID] = None
    link_payment_id: Optional[uuid.UUID] = None
    dismiss: bool = False
    resolution_note: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_mode(self) -> "ExceptionResolveRequest":
        has_link = self.link_invoice_id is not None or self.link_payment_id is not None
        if has_link and self.dismiss:
            raise ValueError("specify either a link (invoice+payment) or dismiss, not both")
        if not has_link and not self.dismiss:
            raise ValueError(
                "must specify either both link_invoice_id and link_payment_id, or dismiss=true"
            )
        if has_link and (self.link_invoice_id is None or self.link_payment_id is None):
            raise ValueError("link mode requires both link_invoice_id and link_payment_id")
        return self
