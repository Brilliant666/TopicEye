"""Central product-profile contract shared by backend startup consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, settings

ProductProfileKey = Literal["topiceye", "rardar"]

RARDAR_NAVIGATION: tuple[tuple[str, str], ...] = (
    ("/", "今日"),
    ("/activity", "动态"),
    ("/discover", "发现"),
    ("/find", "找项目"),
    ("/candidates", "候选池"),
    ("/watchlist", "观察列表"),
)


@dataclass(frozen=True)
class ProductProfile:
    key: ProductProfileKey
    product_name: str
    rardar_enabled: bool
    navigation: tuple[tuple[str, str], ...]


TOPICEYE_PRODUCT_PROFILE = ProductProfile(
    key="topiceye",
    product_name="TopicEye",
    rardar_enabled=False,
    navigation=(),
)

RARDAR_PRODUCT_PROFILE = ProductProfile(
    key="rardar",
    product_name="Rardar",
    rardar_enabled=True,
    navigation=RARDAR_NAVIGATION,
)


def get_product_profile(config: Settings = settings) -> ProductProfile:
    """Return the one active product profile after strict settings validation."""
    return RARDAR_PRODUCT_PROFILE if config.RARDAR_PRODUCT_MODE else TOPICEYE_PRODUCT_PROFILE


def is_rardar_product(config: Settings = settings) -> bool:
    return get_product_profile(config).rardar_enabled


def is_topiceye_product(config: Settings = settings) -> bool:
    return not is_rardar_product(config)
