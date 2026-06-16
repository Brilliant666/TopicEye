"""ai_analyses summary_source

Revision ID: c4e8f1a2b9d3
Revises: b3f7d2a9c1e4
Create Date: 2026-06-16 14:30:00

新增 ai_analyses.summary_source 字段，标记 summary 的真实生成路径：
- llm_pro: Pro 模型直接生成（pro_only / cascade 中 escalated）
- llm_lite: Lite 模型生成（cascade 模式 lite_only 命中）
- local_fallback: LLM 失败后本地兜底（_local_analysis_result）

让前端/周报/分析报告能区分 LLM 真生成 vs 本地兜底，
影响 AI 摘要标签的可信度展示与 LLM 失败率统计。
现有数据留空（NULL），新分析写入时设值。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e8f1a2b9d3'
down_revision = 'b3f7d2a9c1e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('ai_analyses', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'summary_source',
                sa.String(length=32),
                nullable=True,
                comment='llm_pro|llm_lite|local_fallback',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('ai_analyses', schema=None) as batch_op:
        batch_op.drop_column('summary_source')
