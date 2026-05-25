"""
LLM model configuration & evaluation models.

Tables:
  - llm_models: model provider configs (name, model_id, api_key, base_url, enabled, is_default …)
  - model_evaluations: A/B test results for each model on eval prompts
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, Float, Index, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LlmModel(Base):
    __tablename__ = "llm_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="显示名称，如 GLM-5.1")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, comment="litellm provider: openai / custom_zhipu …")
    model_id: Mapped[str] = mapped_column(String(200), nullable=False, comment="litellm model string: openai/glm-5.1")
    api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="API Key (加密存储)")
    api_base: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="自定义 API endpoint")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否为主模型")
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否为备用模型")
    temperature: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_per_1k_input: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="每1k input token 成本(元)")
    cost_per_1k_output: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="每1k output token 成本(元)")
    extra_params: Mapped[Optional[str]] = mapped_column(JSON, nullable=True, comment="额外参数(JSON)")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="CURRENT_TIMESTAMP")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate="CURRENT_TIMESTAMP")

    __table_args__ = (
        Index("ix_llm_models_enabled", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<LlmModel {self.name} ({self.model_id})>"


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="测评批次ID")
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="关联 llm_models.id")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="快照模型名")
    prompt_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="测评类型: analysis/daily_report/weekly_digest/classification")
    prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="使用的 prompt (可选存储)")
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="模型输出")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="响应耗时(毫秒)")
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="输入 token 数")
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="输出 token 数")
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="人工打分 1-5")
    auto_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="自动评分")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="人工备注")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", comment="PENDING/RUNNING/DONE/FAILED")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="CURRENT_TIMESTAMP")

    __table_args__ = (
        Index("ix_model_evals_run_type", "eval_run_id", "prompt_type"),
    )

    def __repr__(self) -> str:
        return f"<ModelEvaluation {self.model_name} {self.prompt_type} {self.status}>"
