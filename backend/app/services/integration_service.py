from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user_integration import UserIntegration

WEREAD_PROVIDER = "weread"
WEREAD_INSTALL_COMMAND = "npx skills add Tencent/WeChatReading -g"
WEREAD_DOCS_URL = "https://weread.qq.com/r/weread-skills"


def api_key_hint(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    stripped = api_key.strip()
    if len(stripped) <= 8:
        return "*" * len(stripped)
    return f"{stripped[:4]}...{stripped[-4:]}"


def _reset_sync_state(integration: UserIntegration) -> None:
    integration.last_sync_at = None
    integration.last_sync_status = None
    integration.last_sync_error = None


async def get_user_integration(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str,
) -> Optional[UserIntegration]:
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
        )
    )
    return result.scalar_one_or_none()


async def upsert_user_integration(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str,
    api_key: str,
    config: Optional[dict[str, Any]] = None,
) -> UserIntegration:
    integration = await get_user_integration(db, user_id=user_id, provider=provider)
    now = datetime.utcnow()
    if integration:
        integration.api_key = api_key.strip()
        integration.config = config or {}
        _reset_sync_state(integration)
        integration.updated_at = now
        await db.flush()
        await db.refresh(integration)
        return integration

    integration = UserIntegration(
        user_id=user_id,
        provider=provider,
        api_key=api_key.strip(),
        config=config or {},
        created_at=now,
        updated_at=now,
    )
    db.add(integration)
    await db.flush()
    await db.refresh(integration)
    return integration


async def clear_user_integration(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str,
) -> bool:
    integration = await get_user_integration(db, user_id=user_id, provider=provider)
    if not integration:
        return False
    integration.api_key = None
    integration.config = {}
    _reset_sync_state(integration)
    integration.updated_at = datetime.utcnow()
    await db.flush()
    return True


def integration_status(integration: Optional[UserIntegration], provider: str) -> dict[str, Any]:
    is_weread = provider == WEREAD_PROVIDER
    return {
        "provider": provider,
        "configured": bool(integration and integration.api_key),
        "api_key_hint": api_key_hint(integration.api_key if integration else None),
        "config": integration.config if integration and isinstance(integration.config, dict) else {},
        "sync_endpoint_configured": bool(str(settings.WEREAD_SKILL_API_URL or "").strip()) if is_weread else False,
        "install_command": WEREAD_INSTALL_COMMAND if is_weread else None,
        "docs_url": WEREAD_DOCS_URL if is_weread else None,
        "last_sync_at": integration.last_sync_at if integration else None,
        "last_sync_status": integration.last_sync_status if integration else None,
        "last_sync_error": integration.last_sync_error if integration else None,
    }
