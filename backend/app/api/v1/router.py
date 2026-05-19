from fastapi import APIRouter
from app.api.v1.sources import router as sources_router
from app.api.v1.contents import router as contents_router
from app.api.v1.topics import router as topics_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.daily_reports import router as daily_reports_router
from app.api.v1.trends import router as trends_router
from app.api.v1.creation import router as creation_router
from app.api.v1.settings import router as settings_router
from app.api.v1.categories import router as categories_router

router = APIRouter(prefix="/api/v1")
router.include_router(sources_router)
router.include_router(contents_router)
router.include_router(topics_router)
router.include_router(analyses_router)
router.include_router(daily_reports_router)
router.include_router(trends_router)
router.include_router(creation_router)
router.include_router(settings_router)
router.include_router(categories_router)
