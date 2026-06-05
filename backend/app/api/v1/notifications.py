"""
站内通知 API。
"""
from __future__ import annotations


from fastapi import APIRouter, Depends, Query

from app.api.v1.auth import get_current_user
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_notifications(
    unread: bool = Query(False, description="只看未读"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """获取通知列表。"""
    notifications = await notification_service.get_notifications(
        unread_only=unread,
        limit=limit,
        offset=offset,
    )
    return {
        "count": len(notifications),
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "category": n.category,
                "title": n.title,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
    }


@router.get("/unread-count")
async def unread_count():
    """获取未读通知数量。"""
    count = await notification_service.get_unread_count()
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int):
    """标记单条通知已读。"""
    ok = await notification_service.mark_read(notification_id)
    return {"success": ok}


@router.post("/read-all")
async def mark_all_read():
    """全部标记已读。"""
    count = await notification_service.mark_all_read()
    return {"marked": count}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: int):
    """删除单条通知。"""
    ok = await notification_service.delete_notification(notification_id)
    return {"success": ok}
