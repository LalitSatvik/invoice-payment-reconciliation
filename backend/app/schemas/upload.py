"""Pydantic schemas for the upload API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PreviewResponse(BaseModel):
    """Response for ``POST /uploads/preview``: raw headers plus a few sample
    rows, rendered positionally (one value per header, in header order) so
    the frontend mapping step can display a simple table before any
    column_map exists.
    """

    headers: List[str]
    sample_rows: List[List[str]]


class UploadBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    original_filename: str
    status: str
    row_count: Optional[int] = None
    error_summary: Optional[str] = None
    source_mapping_id: Optional[uuid.UUID] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
