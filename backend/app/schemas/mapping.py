"""Pydantic schemas for the source-mapping CRUD API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ingestion.csv_parser import REQUIRED_FIELDS

TargetKind = Literal["invoice", "payment"]


class SourceMappingBase(BaseModel):
    source_name: str = Field(min_length=1)
    target_kind: TargetKind
    column_map: Dict[str, str]

    @model_validator(mode="after")
    def _column_map_covers_required_fields(self) -> "SourceMappingBase":
        missing = sorted(REQUIRED_FIELDS - self.column_map.keys())
        if missing:
            raise ValueError(f"column_map is missing required field(s): {missing}")
        return self


class SourceMappingCreate(SourceMappingBase):
    """Request body for ``POST /mappings``."""


class SourceMappingUpdate(SourceMappingBase):
    """Request body for ``PUT /mappings/{id}`` (full replace)."""


class SourceMappingOut(SourceMappingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
