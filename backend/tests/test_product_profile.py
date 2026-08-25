import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.product_profile import (
    RARDAR_NAVIGATION,
    get_product_profile,
    is_rardar_product,
    is_topiceye_product,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres@127.0.0.1:5432/topiceye_test"


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, DATABASE_URL=TEST_DATABASE_URL, **overrides)


def test_product_profile_defaults_to_topiceye() -> None:
    profile = get_product_profile(make_settings())

    assert profile.key == "topiceye"
    assert profile.product_name == "TopicEye"
    assert profile.rardar_enabled is False
    assert profile.navigation == ()


@pytest.mark.parametrize("value", [False, "false", " FALSE ", ""])
def test_product_profile_explicitly_disabled_is_topiceye(value: object) -> None:
    config = make_settings(RARDAR_PRODUCT_MODE=value)

    assert is_topiceye_product(config) is True
    assert is_rardar_product(config) is False


@pytest.mark.parametrize("value", [True, "true", " TRUE "])
def test_product_profile_explicitly_enabled_is_rardar(value: object) -> None:
    config = make_settings(RARDAR_PRODUCT_MODE=value)
    profile = get_product_profile(config)

    assert profile.key == "rardar"
    assert profile.product_name == "Rardar"
    assert profile.navigation == RARDAR_NAVIGATION
    assert profile.navigation == (
        ("/", "今日"),
        ("/activity", "动态"),
        ("/discover", "发现"),
        ("/find", "找项目"),
        ("/candidates", "候选池"),
        ("/watchlist", "观察列表"),
    )


@pytest.mark.parametrize("value", ["1", "yes", "enabled", "rardar", 1])
def test_product_profile_rejects_unknown_values(value: object) -> None:
    with pytest.raises(ValidationError, match="RARDAR_PRODUCT_MODE"):
        make_settings(RARDAR_PRODUCT_MODE=value)
