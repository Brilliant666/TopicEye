"""product_updates: 1 version = 1 record, items[] JSON 列 + seed 8 条版本

把原来 "1 update = 1 row" (title/description/kind/version/status 全在行上) 改成
"1 version = 1 row, items[] JSON 装多条更新". 同时:
- title/description/kind 改 nullable (历史兼容, 新代码不读)
- version 改 NOT NULL
- 加 items JSON NOT NULL DEFAULT '[]'
- 删 ix_product_updates_kind_status, 加 ix_product_updates_version
- 把所有版本记录作为 seed 数据 INSERT 进表 (替代原来写在 Python tuple 里的 BUILTIN)

product_updates 表当前 0 行; seed 之后有 8 个版本记录.
"""
from datetime import date, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c2f4e1b7d3'
down_revision: Union[str, None] = '8a1f4b9d6c7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Seed data: 1 版本 = 1 row, items 是 JSON 数组 ──────────────────────────
_V010 = datetime(2026, 5, 22)
_V011 = datetime(2026, 5, 26)
_V012 = datetime(2026, 5, 29)
_V020 = datetime(2026, 6, 6)
_V021 = datetime(2026, 6, 8)
_V030 = datetime(2026, 6, 14)
_V040_TARGET = date(2026, 9, 30)
_V050_TARGET = date(2026, 12, 31)


def _e(title: str, description: str, kind: str) -> dict:
    """一条 update entry."""
    return {"title": title, "description": description, "kind": kind}


SEED_RECORDS = [
    # v0.5.0 planned
    {
        "version": "v0.5.0", "status": "planned",
        "target_date": _V050_TARGET, "shipped_at": None,
        "created_at": _V030, "updated_at": _V030,
        "items": [
            _e("多用户配额与规模化",
               "LLM 配额按 user_id 分桶（Redis token bucket）；进程内状态外移到 Redis / PG（auth 限流 / LLM 缓存 / job 锁）；认证限流改按用户。触发条件：北极星指标趋势 + 反指标健康。",
               "roadmap"),
        ],
    },
    # v0.4.0 planned
    {
        "version": "v0.4.0", "status": "planned",
        "target_date": _V040_TARGET, "shipped_at": None,
        "created_at": _V030, "updated_at": _V030,
        "items": [
            _e("算法准确性回归看板",
               "继续补齐候选、分析、反馈、摘要之间的验证闭环；当前已在 scoring_flow 接入 feedback_signal，看板 UI 与跨切面回放待补。",
               "roadmap"),
            _e("支付与订阅（先 Stripe）",
               "抽象 PaymentGateway 协议，先接 Stripe 海外（订阅 + webhook + 客户门户），稳后再加微信/支付宝。订阅数据模型：subscriptions / payment_events / invoices；plan_catalog 改结构化数值。",
               "roadmap"),
        ],
    },
    # v0.3.0 shipped
    {
        "version": "v0.3.0", "status": "shipped",
        "target_date": None, "shipped_at": _V030,
        "created_at": _V030, "updated_at": _V030,
        "items": [
            _e("公共/私有信源双层模型",
               "sources 加 owner_user_id 字段，系统公共信源与用户私有信源隔离；新增 /sources/me 系列端点（GET/POST/PUT/DELETE/sync）；内容列表与详情按归属做可见性过滤。",
               "release"),
            _e("用户专属日报",
               "daily_reports 加归属字段，/daily-reports/me 端点拉用户私有日报；调度器按用户循环生成，并发控制避免 timeout。",
               "release"),
            _e("信源类型扩展：YouTube / Podcast / Newsletter",
               "新增 YouTube、Podcast (RSS) 与 Newsletter 抓取器；创建信源时粘贴 URL 自动识别类型，降低私有信源接入门槛。",
               "improvement"),
            _e("网文榜单接入：黑岩 + 点众",
               "黑岩走 biz.zhangwenpindu.cn 公开 CDN API，点众走 _next/data SSG 接口；均无需登录即可抓取书城首页 + 男女频排行榜。",
               "improvement"),
            _e("DuckDB 趋势 top_items JSON 反序列化",
               "PG 端 JSON 列返回字符串、DuckDB 视图读为 string，两条链路都需要 json.loads 后才能送前端；统一在持久化层解码。",
               "fix"),
            _e("trends 边界 NaN 修复",
               "话题趋势分位数截断在边界条件下产生 NaN，导致前端展示为空；改为整数截断并增加守卫。",
               "fix"),
        ],
    },
    # v0.2.1 shipped
    {
        "version": "v0.2.1", "status": "shipped",
        "target_date": None, "shipped_at": _V021,
        "created_at": _V021, "updated_at": _V021,
        "items": [
            _e("反馈与更新工作台",
               "新增 /product-feedback 端点：用户可匿名提交产品问题，管理员可查看/分类/标记修复；前端新增反馈中心页（更新记录 + 问题列表）。",
               "release"),
            _e("匿名问题反馈",
               "未登录用户也可以提交产品问题，后台可以统一查看、处理并标记已修复。",
               "improvement"),
        ],
    },
    # v0.2.0 shipped
    {
        "version": "v0.2.0", "status": "shipped",
        "target_date": None, "shipped_at": _V020,
        "created_at": _V020, "updated_at": _V020,
        "items": [
            _e("AI 分析队列并发化",
               "同步进入的新选题自动进入后台分析队列，减少 pending 堆积并提升整体吞吐；批量分析接口使用并发执行，内容增强批处理也并发化。",
               "release"),
            _e("反馈信号进入算法闭环",
               "用户反馈汇总为评分修正信号，回流到今日精选、摘要候选和算法解释链路。",
               "improvement"),
            _e("网文周报 + 网文雷达原文入口",
               "新增 webnovel 报告服务，按周聚合各平台数据；网文雷达支持点击进入作品详情。",
               "release"),
            _e("计划与权益关联",
               "plans 模型与用户当前权益绑定，为后续 Pro 付费墙做准备。",
               "improvement"),
        ],
    },
    # v0.1.2 shipped
    {
        "version": "v0.1.2", "status": "shipped",
        "target_date": None, "shipped_at": _V012,
        "created_at": _V012, "updated_at": _V012,
        "items": [
            _e("网文雷达：番茄 + 七猫 + 知乎盐选",
               "新增三大网文平台榜单抓取：番茄走 fanqienovel.com API、七猫走 Playwright + Nuxt 解析、知乎盐选走 api.zhihu.com 公开端点。",
               "release"),
            _e("用户反馈机制",
               "用户可对单条内容点赞/点踩，反馈进入算法评分修正。",
               "release"),
            _e("日报/周刊通知推送",
               "日报和周刊生成后通过通知中心推送；前端有未读小红点。",
               "improvement"),
            _e("评分流程诊断",
               "新增 algorithm 评分流程诊断端点，暴露每条内容的评分拆解（质量/热度/相关性/反馈）。",
               "improvement"),
        ],
    },
    # v0.1.1 shipped
    {
        "version": "v0.1.1", "status": "shipped",
        "target_date": None, "shipped_at": _V011,
        "created_at": _V011, "updated_at": _V011,
        "items": [
            _e("多热榜数据源",
               "新增知乎热榜、抖音热榜、Reddit 爬虫；扩展现有 RSS/RSSHub 通用抓取层。",
               "release"),
            _e("数据统计仪表盘",
               "新增 /stats Tab：内容总览 + 信源/分类分布 + 时间趋势 + 网文统计；DuckDB 聚合查询。",
               "release"),
            _e("信源级别采集频率控制",
               "每个 source 可独立配置 fetch_interval_minutes；调度器按各 source 的间隔分桶调度。",
               "improvement"),
            _e("低粉爆文发现",
               "新增 low_follower_viral 算法：在低粉丝信源中识别异常热度信号。",
               "improvement"),
        ],
    },
    # v0.1.0 shipped (MVP)
    {
        "version": "v0.1.0", "status": "shipped",
        "target_date": None, "shipped_at": _V010,
        "created_at": _V010, "updated_at": _V010,
        "items": [
            _e("全栈项目初始化",
               "FastAPI + Next.js + SQLAlchemy + DuckDB；项目骨架、Repository 层、调度器、全局异常处理。",
               "release"),
            _e("AI 日报",
               "每日基于内容池生成日报；支持历史按日期查询；推送通知。",
               "release"),
            _e("多维信号评分引擎",
               "实现质量/热度/相关性/反馈四维评分；今日精选按 curation_score 排序；支持忽略/不感兴趣。",
               "release"),
            _e("首页筛选 + 精选分可视化",
               "首页支持 sort_by/cate/source 筛选；精选分柱状图组件；忽略按钮 + 类型扩展。",
               "improvement"),
            _e("AI 分析（中英文差异化 prompt）",
               "分析服务按内容语言选不同 prompt；摘要 + 角度 + 选题建议一体输出。",
               "improvement"),
            _e("LLM 实时分类",
               "动态分类创建 + 关键词降级兜底；分类可在运行时由 LLM 扩展。",
               "improvement"),
            _e("收藏夹（localStorage 持久化）",
               "前端 favorites 通过 localStorage 跨会话保留；强化类型安全，移除 as any 绕过。",
               "improvement"),
        ],
    },
]


def upgrade() -> None:
    # 1) 加新列 (nullable 先加, 后填默认, 再 NOT NULL)
    with op.batch_alter_table('product_updates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('items', sa.JSON(), nullable=True))

    # 2) 回填默认空数组 (现有 0 行, 兜底用)
    op.execute("UPDATE product_updates SET items = '[]' WHERE items IS NULL")

    # 3) NOT NULL + 字段约束 + 索引调整
    with op.batch_alter_table('product_updates', schema=None) as batch_op:
        batch_op.alter_column('items',
                              existing_type=sa.JSON(),
                              nullable=False,
                              server_default=sa.text("'[]'"))
        batch_op.alter_column('version',
                              existing_type=sa.String(length=50),
                              nullable=False)
        batch_op.alter_column('title',
                              existing_type=sa.String(length=200),
                              nullable=True)
        batch_op.alter_column('description',
                              existing_type=sa.Text(),
                              nullable=True)
        batch_op.alter_column('kind',
                              existing_type=sa.String(length=20),
                              nullable=True)
        batch_op.drop_index('ix_product_updates_kind_status')
        batch_op.create_index('ix_product_updates_version', ['version'], unique=False)

    # 4) Seed 8 条版本记录
    product_updates = sa.table(
        'product_updates',
        sa.column('version', sa.String),
        sa.column('status', sa.String),
        sa.column('target_date', sa.Date),
        sa.column('shipped_at', sa.DateTime),
        sa.column('items', sa.JSON),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(product_updates, [
        {
            "version": r["version"],
            "status": r["status"],
            "target_date": r["target_date"],
            "shipped_at": r["shipped_at"],
            # items 直接传 list, alembic + psycopg 会序列化为 PG jsonb/json
            "items": r["items"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in SEED_RECORDS
    ])


def downgrade() -> None:
    # 1) 删除 seed 记录 (按版本号筛)
    seed_versions = tuple(r["version"] for r in SEED_RECORDS)
    op.execute(
        f"DELETE FROM product_updates WHERE version IN ({','.join(repr(v) for v in seed_versions)})"
    )

    # 2) 回滚 schema
    with op.batch_alter_table('product_updates', schema=None) as batch_op:
        batch_op.drop_index('ix_product_updates_version')
        batch_op.create_index('ix_product_updates_kind_status', ['kind', 'status'], unique=False)
        batch_op.alter_column('kind',
                              existing_type=sa.String(length=20),
                              nullable=False)
        batch_op.alter_column('description',
                              existing_type=sa.Text(),
                              nullable=False)
        batch_op.alter_column('title',
                              existing_type=sa.String(length=200),
                              nullable=False)
        batch_op.alter_column('version',
                              existing_type=sa.String(length=50),
                              nullable=True)
        batch_op.alter_column('items',
                              existing_type=sa.JSON(),
                              nullable=True)
        batch_op.drop_column('items')
