from __future__ import annotations

from fastapi import APIRouter

from app.schemas.plan import PlanCatalogResponse
from app.services.plan_catalog import get_plan_catalog

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=PlanCatalogResponse)
async def list_plans():
    """Return product-plan boundaries for free and paid feature areas."""
    return get_plan_catalog()
