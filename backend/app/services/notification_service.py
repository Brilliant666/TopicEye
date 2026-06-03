"""
站内通知服务。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select, update, delete, func

from app.core.database import async_session
from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def push_notification(
    type: str,
    category: str,
    title: str,
    message: str,
) -> Notification:
    """推送一条站内通知。"""
    async with async_session() as db:
        notif = Notification(
            type=type,
            category=category,
            title=title,
            message=message,
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        logger.info(f"通知推送: [{type}] {title}")
        return notif


async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    """获取通知列表。"""
    async with async_session() as db:
        query = select(Notification).order_by(Notification.created_at.desc())
        if unread_only:
            query = query.where(Notification.is_read == False)
        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())


async def get_unread_count() -> int:
    """获取未读通知数量。"""
    async with async_session() as db:
        result = await db.execute(
            select(func.count(Notification.id)).where(Notification.is_read == False)
        )
        return result.scalar() or 0


async def mark_read(notification_id: int) -> bool:
    """标记单条通知已读。"""
    async with async_session() as db:
        result = await db.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(is_read=True)
        )
        await db.commit()
        return result.rowcount > 0


async def mark_all_read() -> int:
    """全部标记已读。"""
    async with async_session() as db:
        result = await db.execute(
            update(Notification)
            .where(Notification.is_read == False)
            .values(is_read=True)
        )
        await db.commit()
        return result.rowcount


async def delete_notification(notification_id: int) -> bool:
    """删除单条通知。"""
    async with async_session() as db:
        result = await db.execute(
            delete(Notification).where(Notification.id == notification_id)
        )
        await db.commit()
        return result.rowcount > 0
