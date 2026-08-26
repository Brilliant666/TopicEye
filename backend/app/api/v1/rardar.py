"""Rardar-mode read-only product APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.product_profile import is_rardar_product
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError
from app.services.rardar_intelligence import load_explosion_board

router = APIRouter(prefix="/rardar", tags=["rardar"])


@router.get("/explosion-board", response_model=ExplosionBoardResponse)
def explosion_board() -> ExplosionBoardResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return load_explosion_board()
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc
