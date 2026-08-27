"""Rardar-mode read-only product APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.product_profile import is_rardar_product
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError
from app.schemas.rardar_product import (
    FindProjectRequest,
    FindProjectResponse,
    ProjectExplanationRequest,
    ProjectExplanationResponse,
)
from app.services.rardar_intelligence import load_explosion_board
from app.services.rardar_product import RardarProductError, explain_project, find_projects

router = APIRouter(prefix="/rardar", tags=["rardar"])


@router.get("/explosion-board", response_model=ExplosionBoardResponse)
def explosion_board() -> ExplosionBoardResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return load_explosion_board()
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/projects/explain", response_model=ProjectExplanationResponse)
async def project_explanation(payload: ProjectExplanationRequest) -> ProjectExplanationResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return await explain_project(payload)
    except RardarProductError as exc:
        status_code = 409 if exc.code == "rardar_project_revision_changed" else 404
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/find-projects", response_model=FindProjectResponse)
async def find_project_candidates(payload: FindProjectRequest) -> FindProjectResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    return await find_projects(payload)
