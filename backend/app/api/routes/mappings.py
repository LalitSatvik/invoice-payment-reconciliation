"""CRUD endpoints for saved source (column) mappings."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SourceMapping
from app.schemas.mapping import SourceMappingCreate, SourceMappingOut, SourceMappingUpdate

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get("", response_model=List[SourceMappingOut])
def list_mappings(db: Session = Depends(get_db)) -> List[SourceMapping]:
    return db.query(SourceMapping).order_by(SourceMapping.source_name).all()


@router.post("", response_model=SourceMappingOut, status_code=201)
def create_mapping(
    payload: SourceMappingCreate, db: Session = Depends(get_db)
) -> SourceMapping:
    existing = (
        db.query(SourceMapping)
        .filter(SourceMapping.source_name == payload.source_name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"a source mapping named {payload.source_name!r} already exists",
        )
    mapping = SourceMapping(**payload.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("/{mapping_id}", response_model=SourceMappingOut)
def get_mapping(mapping_id: uuid.UUID, db: Session = Depends(get_db)) -> SourceMapping:
    mapping = db.get(SourceMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"source mapping {mapping_id} not found")
    return mapping


@router.put("/{mapping_id}", response_model=SourceMappingOut)
def update_mapping(
    mapping_id: uuid.UUID, payload: SourceMappingUpdate, db: Session = Depends(get_db)
) -> SourceMapping:
    mapping = db.get(SourceMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"source mapping {mapping_id} not found")

    if payload.source_name != mapping.source_name:
        conflict = (
            db.query(SourceMapping)
            .filter(
                SourceMapping.source_name == payload.source_name,
                SourceMapping.id != mapping_id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail=f"a source mapping named {payload.source_name!r} already exists",
            )

    mapping.source_name = payload.source_name
    mapping.target_kind = payload.target_kind
    mapping.column_map = payload.column_map
    db.commit()
    db.refresh(mapping)
    return mapping
