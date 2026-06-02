from app.services.plan_catalog import get_plan_catalog


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
