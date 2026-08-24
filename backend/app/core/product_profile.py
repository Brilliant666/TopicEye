"""Central product-profile switch for the Rardar vertical POC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass(frozen=True)
class ProductProfile:
    key: str
    enabled: bool
    product_name: str
    fixture_root: Path
    ai_provider: str
    ai_model: str
    ai_routing_group: str
    ai_provider_mode: str
    navigation: tuple[tuple[str, str], ...]


def get_product_profile() -> ProductProfile:
    fixture_root = (
        Path(settings.RARDAR_FIXTURE_ROOT).expanduser()
        if settings.RARDAR_FIXTURE_ROOT.strip()
        else Path(__file__).resolve().parent.parent / "rardar" / "fixtures"
    )
    return ProductProfile(
        key="rardar-poc" if settings.RARDAR_PRODUCT_MODE else "topiceye",
        enabled=settings.RARDAR_PRODUCT_MODE,
        product_name="Rardar" if settings.RARDAR_PRODUCT_MODE else "TopicEye",
        fixture_root=fixture_root.resolve(),
        ai_provider="mock_sub2api",
        ai_model="gpt-5.6-sol",
        ai_routing_group=settings.RARDAR_AI_ROUTING_GROUP.strip() or "rardar_poc",
        ai_provider_mode="deterministic_mock",
        navigation=(
            ("/", "今日"),
            ("/signals", "动态"),
            ("/discover", "发现"),
            ("/find-project", "找项目"),
            ("/candidates", "候选池"),
            ("/watchlist", "观察列表"),
        ),
    )
