import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import plans as plans_api
from app.core.database import Base
from app.services.auth_service import create_session, create_user
from app.services.plan_catalog import get_plan_catalog, get_plan_catalog_for_user, get_tier_by_key


def test_plan_catalog_declares_free_and_paid_boundaries():
    catalog = get_plan_catalog()
    tiers = {tier["key"]: tier for tier in catalog["tiers"]}

    assert {"free", "pro", "studio", "enterprise"} == set(tiers)
    assert tiers["free"]["limits"]["custom_sources"] == 0
    assert tiers["pro"]["recommended"] is True
    assert "每日查看部分今日选题" in tiers["free"]["features"]
    assert "AI 选题转化" in tiers["pro"]["features"]
    assert "自定义信源" in tiers["studio"]["features"]
    assert "API 接入" in tiers["enterprise"]["features"]
    assert catalog["free_area"]
    assert catalog["paid_area"]


def test_plan_catalog_resolves_current_user_tier():
    assert get_tier_by_key("pro")["name"] == "Pro 版"
    assert get_tier_by_key("missing")["key"] == "free"

    catalog = get_plan_catalog_for_user("studio")

    assert catalog["current_plan"] == "studio"
    assert catalog["current_tier"]["limits"]["team_members"] == 5


@pytest.mark.asyncio
async def test_plans_api_resolves_current_plan_from_bearer_token(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(plans_api, "async_session", session_factory)

    async with session_factory() as db:
        user = await create_user(db, email="plan@example.com", password="Password123")
        user.plan = "studio"
        token, _session = await create_session(db, user)
        await db.commit()

    catalog = await plans_api.list_plans(authorization=f"Bearer {token}")

    assert catalog["current_plan"] == "studio"
    assert catalog["current_tier"]["name"] == "Studio 版"
    await engine.dispose()
