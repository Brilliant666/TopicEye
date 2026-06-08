from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.models.product_feedback import ProductUpdateKind, ProductUpdateStatus
from app.schemas.product_feedback import ProductUpdateResponse


BUILTIN_PRODUCT_UPDATES: tuple[ProductUpdateResponse, ...] = (
    ProductUpdateResponse(
        id=-1,
        title="AI 分析队列并发化",
        description="同步进入的新选题会自动进入后台分析队列，减少 pending 堆积并提升整体吞吐。",
        kind=ProductUpdateKind.release,
        status=ProductUpdateStatus.shipped,
        version="v0.2.0",
        target_date=None,
        shipped_at=datetime(2026, 6, 8, 0, 0, 0),
        created_by_id=None,
        created_at=datetime(2026, 6, 8, 0, 0, 0),
        updated_at=datetime(2026, 6, 8, 0, 0, 0),
    ),
    ProductUpdateResponse(
        id=-2,
        title="反馈信号进入算法闭环",
        description="用户反馈会汇总为评分修正信号，并回流到今日精选、摘要候选和算法解释链路。",
        kind=ProductUpdateKind.improvement,
        status=ProductUpdateStatus.shipped,
        version="v0.2.0",
        target_date=None,
        shipped_at=datetime(2026, 6, 8, 0, 0, 0),
        created_by_id=None,
        created_at=datetime(2026, 6, 8, 0, 0, 0),
        updated_at=datetime(2026, 6, 8, 0, 0, 0),
    ),
    ProductUpdateResponse(
        id=-3,
        title="匿名问题反馈",
        description="未登录用户也可以提交产品问题，后台可以统一查看、处理并标记已修复。",
        kind=ProductUpdateKind.fix,
        status=ProductUpdateStatus.shipped,
        version="v0.2.1",
        target_date=None,
        shipped_at=datetime(2026, 6, 8, 0, 0, 0),
        created_by_id=None,
        created_at=datetime(2026, 6, 8, 0, 0, 0),
        updated_at=datetime(2026, 6, 8, 0, 0, 0),
    ),
    ProductUpdateResponse(
        id=-4,
        title="算法准确性回归看板",
        description="继续补齐候选、分析、反馈、摘要之间的验证闭环，让评分依据更可追踪。",
        kind=ProductUpdateKind.roadmap,
        status=ProductUpdateStatus.in_progress,
        version="v0.3.0",
        target_date=None,
        shipped_at=None,
        created_by_id=None,
        created_at=datetime(2026, 6, 8, 0, 0, 0),
        updated_at=datetime(2026, 6, 8, 0, 0, 0),
    ),
)


def list_builtin_product_updates(
    *,
    kind: ProductUpdateKind | None = None,
    status: ProductUpdateStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ProductUpdateResponse], int]:
    items: Iterable[ProductUpdateResponse] = BUILTIN_PRODUCT_UPDATES
    if kind is not None:
        items = [item for item in items if item.kind == kind]
    if status is not None:
        items = [item for item in items if item.status == status]

    sorted_items = sorted(
        items,
        key=lambda item: (
            0 if item.status != ProductUpdateStatus.shipped else 1,
            item.shipped_at or item.updated_at,
            abs(item.id),
        ),
        reverse=True,
    )
    return sorted_items[offset:offset + limit], len(sorted_items)
