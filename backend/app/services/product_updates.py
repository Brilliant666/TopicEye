from __future__ import annotations

from datetime import datetime
from typing import Iterable

from app.models.product_feedback import ProductUpdateKind, ProductUpdateStatus
from app.schemas.product_feedback import ProductUpdateResponse


# v0.3.0 集成的 shipped_at 与 T1-1 commit 落库日期一致
_V030_SHIP = datetime(2026, 6, 14, 0, 0, 0)
_V040_TARGET = datetime(2026, 9, 30, 0, 0, 0).date()
_V050_TARGET = datetime(2026, 12, 31, 0, 0, 0).date()


BUILTIN_PRODUCT_UPDATES: tuple[ProductUpdateResponse, ...] = (
    # ── v0.2.0 shipped ───────────────────────────────────────────
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
    # ── v0.2.1 shipped ───────────────────────────────────────────
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
    # ── v0.3.0 shipped（公共/私有双层模型 + 用户日报 + 网文榜单） ─
    ProductUpdateResponse(
        id=-5,
        title="公共/私有信源双层模型",
        description=(
            "新增 sources.owner_user_id 字段，系统公共信源与用户私有信源隔离；"
            "新增 /sources/me 系列端点（GET/POST/PUT/DELETE/sync），"
            "内容列表与详情按归属做可见性过滤。"
        ),
        kind=ProductUpdateKind.release,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-6,
        title="用户专属日报",
        description=(
            "daily_reports 加归属字段，/daily-reports/me 端点拉取用户私有日报；"
            "调度器按用户循环生成，并发控制避免 timeout。"
        ),
        kind=ProductUpdateKind.release,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-7,
        title="网文榜单接入：黑岩 + 点众",
        description=(
            "黑岩走 biz.zhangwenpindu.cn 公开 CDN API，点众走 _next/data SSG 接口，"
            "均无需登录即可抓取书城首页 + 男女频排行榜。"
        ),
        kind=ProductUpdateKind.improvement,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-8,
        title="信源类型扩展：YouTube / Podcast / Newsletter",
        description=(
            "新增 YouTube、Podcast (RSS) 与 Newsletter 抓取器，"
            "创建信源时粘贴 URL 自动识别类型，降低私有信源接入门槛。"
        ),
        kind=ProductUpdateKind.improvement,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-9,
        title="trends 边界 NaN 修复",
        description="话题趋势分位数截断在边界条件下产生 NaN，导致前端展示为空；改为整数截断并增加守卫。",
        kind=ProductUpdateKind.fix,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-10,
        title="DuckDB 趋势 top_items JSON 反序列化",
        description=(
            "PG 端 JSON 列返回字符串、DuckDB 视图读为 string，"
            "两条链路都需要 json.loads 后才能送前端；统一在持久化层解码。"
        ),
        kind=ProductUpdateKind.fix,
        status=ProductUpdateStatus.shipped,
        version="v0.3.0",
        target_date=None,
        shipped_at=_V030_SHIP,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    # ── v0.4.0 planned ──────────────────────────────────────────
    ProductUpdateResponse(
        id=-4,
        title="算法准确性回归看板",
        description=(
            "继续补齐候选、分析、反馈、摘要之间的验证闭环，"
            "让评分依据更可追踪；当前已在 scoring_flow 接入 feedback_signal，"
            "看板 UI 与跨切面回放待补。"
        ),
        kind=ProductUpdateKind.roadmap,
        status=ProductUpdateStatus.planned,
        version="v0.4.0",
        target_date=_V040_TARGET,
        shipped_at=None,
        created_by_id=None,
        created_at=datetime(2026, 6, 8, 0, 0, 0),
        updated_at=_V030_SHIP,
    ),
    ProductUpdateResponse(
        id=-11,
        title="支付与订阅（先 Stripe）",
        description=(
            "抽象 PaymentGateway 协议，先接 Stripe 海外（订阅 + webhook + 客户门户），"
            "稳后再加微信/支付宝。订阅数据模型：subscriptions / payment_events / invoices，"
            "plan_catalog 改结构化数值。"
        ),
        kind=ProductUpdateKind.roadmap,
        status=ProductUpdateStatus.planned,
        version="v0.4.0",
        target_date=_V040_TARGET,
        shipped_at=None,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
    ),
    # ── v0.5.0 planned ──────────────────────────────────────────
    ProductUpdateResponse(
        id=-12,
        title="多用户配额与规模化",
        description=(
            "LLM 配额按 user_id 分桶（Redis token bucket），"
            "进程内状态外移到 Redis / PG（auth 限流 / LLM 缓存 / job 锁），"
            "认证限流改按用户。触发条件：北极星指标趋势 + 反指标健康。"
        ),
        kind=ProductUpdateKind.roadmap,
        status=ProductUpdateStatus.planned,
        version="v0.5.0",
        target_date=_V050_TARGET,
        shipped_at=None,
        created_by_id=None,
        created_at=_V030_SHIP,
        updated_at=_V030_SHIP,
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
