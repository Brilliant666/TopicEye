"""
LLM Model configuration & evaluation API endpoints.

Model Config:
  GET    /models          — list all configured models
  POST   /models          — add a new model config
  PUT    /models/{id}     — update a model config
  DELETE /models/{id}     — delete a model config
  POST   /models/{id}/set-primary   — set as primary model
  POST   /models/{id}/set-fallback  — set as fallback model
  POST   /models/{id}/test          — test connectivity (single prompt)

Evaluation:
  POST   /evaluations/run            — run A/B evaluation across selected models
  GET    /evaluations/runs           — list all eval runs
  GET    /evaluations/runs/{run_id}  — get results for a specific run
  PUT    /evaluations/{id}/score     — human score a single eval result
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, Integer as SAInteger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.sqlite_retry import begin_immediate_for_sqlite, retry_sqlite_locked
from app.models.llm_model import LlmCallLog, LlmModel, ModelEvaluation
from app.services.llm.provider import invalidate_model_cache
from app.services.llm.model_resolver import resolve_litellm_model
from app.services.llm_usage import extract_usage, record_llm_call_in_new_session

router = APIRouter(prefix="/models", tags=["models"])

LLM_COMPLETION_TIMEOUT_SECONDS = 25


def _model_snapshot(model: LlmModel) -> SimpleNamespace:
    return SimpleNamespace(
        id=model.id,
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
        api_key=model.api_key,
        api_base=model.api_base,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        cost_per_1k_input=model.cost_per_1k_input,
        cost_per_1k_output=model.cost_per_1k_output,
        extra_params=model.extra_params,
    )


def _resolve_litellm_model(model: LlmModel) -> str:
    return resolve_litellm_model(model)


def _missing_explicit_api_key(model: LlmModel) -> bool:
    """OpenAI-compatible custom endpoints need an explicit key in this app."""
    return bool(model.api_base) and not bool(model.api_key)


def _completion_kwargs(
    model: LlmModel,
    resolved_model: str,
    messages: list[dict],
    *,
    temperature: float,
    max_tokens: int,
) -> dict:
    kwargs = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": LLM_COMPLETION_TIMEOUT_SECONDS,
    }
    if model.api_key:
        kwargs["api_key"] = model.api_key
    if model.api_base:
        kwargs["api_base"] = model.api_base
    return kwargs


def _sample_payload(sample_content: Optional[str]) -> dict:
    if not sample_content:
        return {
            "title": "OpenAI 发布 GPT-5: 多模态能力大幅提升",
            "content": "OpenAI 今日正式发布 GPT-5 模型，在多模态理解、代码生成和长文本处理方面均有显著提升。"
                       "新模型在多项基准测试中刷新纪录，引发行业广泛讨论。",
        }

    try:
        parsed = json.loads(sample_content)
        if isinstance(parsed, dict):
            return {
                "title": str(parsed.get("title") or "未命名内容"),
                "content": str(parsed.get("content") or parsed.get("summary") or sample_content),
            }
    except json.JSONDecodeError:
        pass

    return {"title": sample_content[:80], "content": sample_content}


def _extract_json_candidate(content: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else content.strip()


def _auto_score_response(content: str) -> float:
    if not content:
        return 0.0

    auto_score = 2.0
    candidate = _extract_json_candidate(content)
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict) and parsed:
            auto_score += 2.0
            auto_score += min(len(parsed.keys()) * 0.2, 1.0)
        elif isinstance(parsed, list) and parsed:
            auto_score += 1.5
        else:
            auto_score += 0.5
    except json.JSONDecodeError:
        if len(content) > 50:
            auto_score += 1.0

    return round(min(5.0, auto_score), 1)


async def _normalize_model_roles(db: AsyncSession, models: list[LlmModel]) -> None:
    """Repair duplicate role flags from older writes before returning configs."""
    primary_seen = False
    fallback_seen = False
    dirty = False

    for model in models:
        if model.is_primary:
            if primary_seen:
                model.is_primary = False
                dirty = True
            else:
                primary_seen = True

        if model.is_fallback:
            if model.is_primary or fallback_seen:
                model.is_fallback = False
                dirty = True
            else:
                fallback_seen = True

    if dirty:
        await db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────

class ModelCreateRequest(BaseModel):
    name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="litellm provider")
    model_id: str = Field(..., description="litellm model string")
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    enabled: bool = True
    temperature: float = 0.3
    max_tokens: int = 2000
    requests_per_minute: int = 60
    description: Optional[str] = None
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None
    cost_per_1m_input: Optional[float] = None
    cost_per_1m_input_cache_hit: Optional[float] = None
    cost_per_1m_output: Optional[float] = None
    extra_params: Optional[dict] = None


class ModelUpdateRequest(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    enabled: Optional[bool] = None
    is_primary: Optional[bool] = None
    is_fallback: Optional[bool] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    requests_per_minute: Optional[int] = None
    description: Optional[str] = None
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None
    cost_per_1m_input: Optional[float] = None
    cost_per_1m_input_cache_hit: Optional[float] = None
    cost_per_1m_output: Optional[float] = None
    extra_params: Optional[dict] = None


class EvalRunRequest(BaseModel):
    """Request to run an A/B evaluation."""
    model_ids: list[int] = Field(..., description="要对比的模型 ID 列表")
    prompt_type: str = Field("analysis", description="测评类型: analysis/daily_report/weekly_digest/classification/custom")
    custom_prompt: Optional[str] = Field(None, description="自定义 prompt (prompt_type=custom 时必填)")
    sample_content: Optional[str] = Field(None, description="用于测评的内容样例(JSON)")


class ScoreRequest(BaseModel):
    quality_score: float = Field(..., ge=1, le=5, description="人工打分 1-5")
    notes: Optional[str] = None


async def _retry_write(db: AsyncSession, operation):
    async def _wrapped():
        await begin_immediate_for_sqlite(db)
        return await operation()

    return await retry_sqlite_locked(_wrapped, on_retry=db.rollback)


async def _retry_write_and_invalidate_models(db: AsyncSession, operation):
    result = await _retry_write(db, operation)
    await db.commit()
    await invalidate_model_cache()
    return result


def _per_1k_to_1m(value: Optional[float]) -> Optional[float]:
    return round(value * 1000, 6) if value is not None else None


def _per_1m_to_1k(value: Optional[float]) -> Optional[float]:
    return round(value / 1000, 9) if value is not None else None


def _pricing_extra_params(extra_params: Optional[dict], cache_hit_price: Optional[float]) -> Optional[dict]:
    params = dict(extra_params or {})
    if cache_hit_price is None:
        params.pop("cost_per_1m_input_cache_hit", None)
    else:
        params["cost_per_1m_input_cache_hit"] = cache_hit_price
    if any(key.startswith("cost_per_1m_") for key in params):
        params.setdefault("pricing_unit", "per_1m_tokens")
    return params or None


def _model_cost_input(req: ModelCreateRequest | ModelUpdateRequest) -> Optional[float]:
    if req.cost_per_1m_input is not None:
        return _per_1m_to_1k(req.cost_per_1m_input)
    return req.cost_per_1k_input


def _model_cost_output(req: ModelCreateRequest | ModelUpdateRequest) -> Optional[float]:
    if req.cost_per_1m_output is not None:
        return _per_1m_to_1k(req.cost_per_1m_output)
    return req.cost_per_1k_output


def _model_payload(m: LlmModel) -> dict:
    extra_params = m.extra_params if isinstance(m.extra_params, dict) else {}
    return {
        "id": m.id,
        "name": m.name,
        "provider": m.provider,
        "model_id": m.model_id,
        "api_base": m.api_base,
        "api_key_set": bool(m.api_key),
        "enabled": m.enabled,
        "is_primary": m.is_primary,
        "is_fallback": m.is_fallback,
        "temperature": m.temperature,
        "max_tokens": m.max_tokens,
        "requests_per_minute": m.requests_per_minute,
        "description": m.description,
        "cost_per_1k_input": m.cost_per_1k_input,
        "cost_per_1k_output": m.cost_per_1k_output,
        "cost_per_1m_input": _per_1k_to_1m(m.cost_per_1k_input),
        "cost_per_1m_input_cache_hit": extra_params.get("cost_per_1m_input_cache_hit"),
        "cost_per_1m_output": _per_1k_to_1m(m.cost_per_1k_output),
        "extra_params": m.extra_params,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


# ── Model Config CRUD ─────────────────────────────────────────────────

@router.get("")
async def list_models(db: AsyncSession = Depends(get_db)):
    """List all configured LLM models."""
    result = await db.execute(select(LlmModel).order_by(LlmModel.id))
    models = result.scalars().all()
    await _normalize_model_roles(db, models)
    return {
        "models": [_model_payload(m) for m in models],
        "total": len(models),
    }


@router.post("")
async def create_model(req: ModelCreateRequest, db: AsyncSession = Depends(get_db)):
    """Add a new LLM model configuration."""
    async def _create():
        model = LlmModel(
            name=req.name,
            provider=req.provider,
            model_id=req.model_id,
            api_key=req.api_key,
            api_base=req.api_base,
            enabled=req.enabled,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            requests_per_minute=req.requests_per_minute,
            description=req.description,
            cost_per_1k_input=_model_cost_input(req),
            cost_per_1k_output=_model_cost_output(req),
            extra_params=_pricing_extra_params(req.extra_params, req.cost_per_1m_input_cache_hit),
        )
        db.add(model)
        await db.flush()
        return {"id": model.id, "name": model.name, "message": "模型配置创建成功"}

    return await _retry_write_and_invalidate_models(db, _create)


@router.get("/usage/summary")
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Summarize token usage and estimated cost from request-level LLM call logs."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(LlmCallLog, LlmModel)
        .join(LlmModel, LlmCallLog.model_id == LlmModel.id, isouter=True)
        .where(LlmCallLog.created_at >= since)
        .order_by(desc(LlmCallLog.created_at))
    )
    rows = result.all()

    by_model: dict[int, dict] = {}
    by_prompt: dict[str, dict] = {}
    totals = {
        "calls": 0,
        "success_calls": 0,
        "failed_calls": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "billable_input_tokens": 0,
        "estimated_cost": 0.0,
        "duration_ms": 0,
    }

    for call_log, model in rows:
        tokens_input = call_log.input_tokens or 0
        tokens_output = call_log.output_tokens or 0
        estimated_cost = call_log.total_cost or 0
        is_done = call_log.status == "DONE"
        is_failed = call_log.status == "FAILED"

        totals["calls"] += 1
        totals["success_calls"] += 1 if is_done else 0
        totals["failed_calls"] += 1 if is_failed else 0
        totals["tokens_input"] += tokens_input
        totals["tokens_output"] += tokens_output
        totals["cache_read_tokens"] += call_log.cache_read_tokens or 0
        totals["cache_creation_tokens"] += call_log.cache_creation_tokens or 0
        totals["billable_input_tokens"] += call_log.billable_input_tokens or 0
        totals["estimated_cost"] += estimated_cost
        totals["duration_ms"] += call_log.duration_ms or 0

        model_key = call_log.model_id or 0
        if model_key not in by_model:
            by_model[model_key] = {
                "model_id": call_log.model_id,
                "model_name": model.name if model else (call_log.model_name or call_log.actual_model or "未配置模型"),
                "provider": model.provider if model else call_log.provider,
                "calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "billable_input_tokens": 0,
                "estimated_cost": 0.0,
                "avg_duration_ms": 0,
                "cost_per_1k_input": model.cost_per_1k_input if model else None,
                "cost_per_1k_output": model.cost_per_1k_output if model else None,
                "cost_per_1m_input": _per_1k_to_1m(model.cost_per_1k_input) if model else None,
                "cost_per_1m_input_cache_hit": (
                    model.extra_params.get("cost_per_1m_input_cache_hit")
                    if model and isinstance(model.extra_params, dict)
                    else None
                ),
                "cost_per_1m_output": _per_1k_to_1m(model.cost_per_1k_output) if model else None,
            }
        model_stats = by_model[model_key]
        model_stats["calls"] += 1
        model_stats["success_calls"] += 1 if is_done else 0
        model_stats["failed_calls"] += 1 if is_failed else 0
        model_stats["tokens_input"] += tokens_input
        model_stats["tokens_output"] += tokens_output
        model_stats["cache_read_tokens"] += call_log.cache_read_tokens or 0
        model_stats["cache_creation_tokens"] += call_log.cache_creation_tokens or 0
        model_stats["billable_input_tokens"] += call_log.billable_input_tokens or 0
        model_stats["estimated_cost"] += estimated_cost
        model_stats["avg_duration_ms"] += call_log.duration_ms or 0

        prompt_key = call_log.scene
        if prompt_key not in by_prompt:
            by_prompt[prompt_key] = {
                "prompt_type": prompt_key,
                "calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "billable_input_tokens": 0,
                "estimated_cost": 0.0,
            }
        prompt_stats = by_prompt[prompt_key]
        prompt_stats["calls"] += 1
        prompt_stats["success_calls"] += 1 if is_done else 0
        prompt_stats["failed_calls"] += 1 if is_failed else 0
        prompt_stats["tokens_input"] += tokens_input
        prompt_stats["tokens_output"] += tokens_output
        prompt_stats["cache_read_tokens"] += call_log.cache_read_tokens or 0
        prompt_stats["cache_creation_tokens"] += call_log.cache_creation_tokens or 0
        prompt_stats["billable_input_tokens"] += call_log.billable_input_tokens or 0
        prompt_stats["estimated_cost"] += estimated_cost

    for stats in by_model.values():
        stats["estimated_cost"] = round(stats["estimated_cost"], 6)
        stats["avg_duration_ms"] = int(stats["avg_duration_ms"] / stats["calls"]) if stats["calls"] else 0

    for stats in by_prompt.values():
        stats["estimated_cost"] = round(stats["estimated_cost"], 6)

    total_tokens = totals["tokens_input"] + totals["tokens_output"]
    avg_duration = int(totals["duration_ms"] / totals["calls"]) if totals["calls"] else 0
    success_rate = round(totals["success_calls"] / totals["calls"], 4) if totals["calls"] else 0

    return {
        "days": days,
        "since": since.isoformat(),
        "total": {
            "calls": totals["calls"],
            "success_calls": totals["success_calls"],
            "failed_calls": totals["failed_calls"],
            "tokens_input": totals["tokens_input"],
            "tokens_output": totals["tokens_output"],
            "cache_read_tokens": totals["cache_read_tokens"],
            "cache_creation_tokens": totals["cache_creation_tokens"],
            "billable_input_tokens": totals["billable_input_tokens"],
            "tokens_total": total_tokens,
            "estimated_cost": round(totals["estimated_cost"], 6),
            "avg_duration_ms": avg_duration,
            "success_rate": success_rate,
        },
        "by_model": sorted(by_model.values(), key=lambda item: item["estimated_cost"], reverse=True),
        "by_prompt": sorted(by_prompt.values(), key=lambda item: item["estimated_cost"], reverse=True),
    }


@router.put("/{model_id}")
async def update_model(model_id: int, req: ModelUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update an existing model configuration."""
    async def _update():
        result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
        model = result.scalar_one_or_none()
        if not model:
            raise HTTPException(404, f"Model {model_id} not found")

        update_data = req.model_dump(exclude_unset=True)
        for api_only_key in ("cost_per_1m_input", "cost_per_1m_input_cache_hit", "cost_per_1m_output"):
            update_data.pop(api_only_key, None)
        if "cost_per_1m_input" in req.model_fields_set:
            update_data["cost_per_1k_input"] = _per_1m_to_1k(req.cost_per_1m_input)
        if "cost_per_1m_output" in req.model_fields_set:
            update_data["cost_per_1k_output"] = _per_1m_to_1k(req.cost_per_1m_output)
        if "cost_per_1m_input_cache_hit" in req.model_fields_set:
            update_data["extra_params"] = _pricing_extra_params(
                update_data.get("extra_params", model.extra_params),
                req.cost_per_1m_input_cache_hit,
            )
        for key, value in update_data.items():
            setattr(model, key, value)

        # Ensure only one primary / one fallback
        if req.is_primary is True:
            await db.execute(
                LlmModel.__table__.update()
                .where(LlmModel.id != model_id)
                .values(is_primary=False)
            )
            model.is_fallback = False
        if req.is_fallback is True:
            await db.execute(
                LlmModel.__table__.update()
                .where(LlmModel.id != model_id)
                .values(is_fallback=False)
            )
            model.is_primary = False

        await db.flush()
        return {"message": f"模型 {model.name} 更新成功"}

    return await _retry_write_and_invalidate_models(db, _update)


@router.delete("/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a model configuration."""
    async def _delete():
        result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
        model = result.scalar_one_or_none()
        if not model:
            raise HTTPException(404, f"Model {model_id} not found")
        name = model.name
        await db.delete(model)
        await db.flush()
        return {"message": f"模型 {name} 已删除"}

    return await _retry_write_and_invalidate_models(db, _delete)


@router.post("/{model_id}/set-primary")
async def set_primary(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the primary model (unset others)."""
    async def _set_primary():
        result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
        model = result.scalar_one_or_none()
        if not model:
            raise HTTPException(404, f"Model {model_id} not found")

        await db.execute(LlmModel.__table__.update().values(is_primary=False))
        model.is_primary = True
        model.is_fallback = False
        model.enabled = True
        await db.flush()
        return {"message": f"{model.name} 已设为主模型"}

    return await _retry_write_and_invalidate_models(db, _set_primary)


@router.post("/{model_id}/set-fallback")
async def set_fallback(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the fallback model."""
    async def _set_fallback():
        result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
        model = result.scalar_one_or_none()
        if not model:
            raise HTTPException(404, f"Model {model_id} not found")

        await db.execute(LlmModel.__table__.update().values(is_fallback=False))
        model.is_fallback = True
        model.is_primary = False
        model.enabled = True
        await db.flush()
        return {"message": f"{model.name} 已设为备用模型"}

    return await _retry_write_and_invalidate_models(db, _set_fallback)


@router.post("/{model_id}/test")
async def test_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Test a model by sending a simple prompt."""
    from litellm import completion

    result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, f"Model {model_id} not found")

    if _missing_explicit_api_key(model):
        return {
            "status": "failed",
            "model_name": model.name,
            "error": "模型配置缺少 API Key，请在模型配置中补充后再测试。",
            "duration_ms": 0,
        }

    resolved_model = _resolve_litellm_model(model)

    test_prompt = "请用一句话介绍你自己，包括你的模型名称。"
    kwargs = _completion_kwargs(
        model,
        resolved_model,
        [{"role": "user", "content": test_prompt}],
        temperature=0.3,
        max_tokens=200,
    )

    start = time.monotonic()
    try:
        response = await asyncio.to_thread(completion, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)
        content = response.choices[0].message.content or ""
        usage = extract_usage(response)
        await record_llm_call_in_new_session(
            model=model,
            request_model=resolved_model,
            scene="model_test",
            status="DONE",
            duration_ms=duration_ms,
            usage=usage,
        )
        return {
            "status": "success",
            "model_name": model.name,
            "response": content,
            "duration_ms": duration_ms,
            "tokens_input": usage.input_tokens,
            "tokens_output": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_creation_tokens": usage.cache_creation_tokens,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        await record_llm_call_in_new_session(
            model=model,
            request_model=resolved_model,
            scene="model_test",
            status="FAILED",
            duration_ms=duration_ms,
            error_message=str(e),
        )
        return {
            "status": "failed",
            "model_name": model.name,
            "error": str(e),
            "duration_ms": duration_ms,
        }


# ── Evaluation A/B ────────────────────────────────────────────────────

# Standard test prompts for each type
EVAL_PROMPTS = {
    "analysis": """分析以下内容的选题价值，从创作者角度评估。

标题：{title}
内容摘要：{content}

请以 JSON 格式返回：
{{
  "creator_score": 0-100,
  "viral_score": 0-100,
  "quality_score": 0-100,
  "summary": "一句话总结",
  "recommendation": "选题建议(50字内)",
  "tags": ["标签1", "标签2", "标签3"]
}}""",
    "daily_report": """基于以下今日热门内容，生成一份创作者日报摘要。

热门内容（前5条）：
{content}

请以 JSON 格式返回：
{{
  "overview": "今日概述(100字)",
  "takeaway": "今日要点(50字)",
  "keywords": ["关键词1", "关键词2"],
  "trends": [{{"title": "趋势名", "desc": "描述"}}]
}}""",
    "weekly_digest": """基于以下本周热门内容，生成一份创作者周刊摘要。

本周热门内容：
{content}

请以 JSON 格式返回：
{{
  "overview": "本周概述(150字)",
  "takeaway": "本周要点(50字)",
  "keywords": ["关键词1", "关键词2"],
  "trends": [{{"title": "趋势名", "desc": "描述"}}],
  "top_picks": [{{"title": "选题", "reason": "推荐理由"}}]
}}""",
    "classification": """对以下内容进行分类。

标题：{title}

请返回 JSON：
{{
  "category": "分类名",
  "subcategory": "子分类",
  "confidence": 0.0-1.0
}}""",
}


@router.post("/evaluations/run")
async def run_evaluation(req: EvalRunRequest, db: AsyncSession = Depends(get_db)):
    """Run an A/B evaluation across selected models with the same prompt."""
    from litellm import completion

    # Fetch models
    result = await db.execute(
        select(LlmModel).where(LlmModel.id.in_(req.model_ids), LlmModel.enabled == True)
    )
    models = [_model_snapshot(model) for model in result.scalars().all()]
    if not models:
        raise HTTPException(400, "没有找到启用的模型")
    await db.rollback()

    # Build prompt
    prompt_template = EVAL_PROMPTS.get(req.prompt_type)
    if req.prompt_type == "custom" and req.custom_prompt:
        prompt_template = req.custom_prompt
    if not prompt_template:
        raise HTTPException(400, f"未知的测评类型: {req.prompt_type}")

    sample = _sample_payload(req.sample_content)
    prompt_text = prompt_template.format(title=sample["title"], content=sample["content"])

    # Create eval run
    eval_run_id = f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

    evaluations = []
    async def _create_records():
        for model in models:
            eval_record = ModelEvaluation(
                eval_run_id=eval_run_id,
                model_id=model.id,
                model_name=model.name,
                prompt_type=req.prompt_type,
                prompt_text=prompt_text[:2000],
                status="PENDING",
            )
            db.add(eval_record)
            evaluations.append((model, eval_record))
        await db.flush()

    await _retry_write(db, _create_records)
    await db.commit()

    # Run each model sequentially (avoid rate limits)
    for model, eval_record in evaluations:
        async def _mark_running():
            result = await db.execute(select(ModelEvaluation).where(ModelEvaluation.id == eval_record.id))
            current = result.scalar_one()
            current.status = "RUNNING"
            await db.flush()

        await _retry_write(db, _mark_running)
        await db.commit()

        if _missing_explicit_api_key(model):
            async def _mark_missing_key():
                result = await db.execute(select(ModelEvaluation).where(ModelEvaluation.id == eval_record.id))
                current = result.scalar_one()
                current.status = "FAILED"
                current.error_message = "模型配置缺少 API Key，请在模型配置中补充后再测评。"
                await db.flush()

            await _retry_write(db, _mark_missing_key)
            await db.commit()
            await asyncio.sleep(0.1)
            continue

        resolved_model = _resolve_litellm_model(model)

        kwargs = _completion_kwargs(
            model,
            resolved_model,
            [{"role": "user", "content": prompt_text}],
            temperature=model.temperature,
            max_tokens=model.max_tokens,
        )

        start = time.monotonic()
        try:
            response = await asyncio.to_thread(completion, **kwargs)
            duration_ms = int((time.monotonic() - start) * 1000)
            content = response.choices[0].message.content or ""
            usage = extract_usage(response)

            async def _mark_done():
                result = await db.execute(select(ModelEvaluation).where(ModelEvaluation.id == eval_record.id))
                current = result.scalar_one()
                current.status = "DONE"
                current.response_text = content
                current.duration_ms = duration_ms
                current.tokens_input = usage.input_tokens
                current.tokens_output = usage.output_tokens
                current.auto_score = _auto_score_response(content)
                await db.flush()

            await _retry_write(db, _mark_done)
            await db.commit()
            await record_llm_call_in_new_session(
                model=model,
                request_model=resolved_model,
                scene=f"evaluation:{req.prompt_type}",
                status="DONE",
                duration_ms=duration_ms,
                usage=usage,
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_message = str(e)

            async def _mark_failed():
                result = await db.execute(select(ModelEvaluation).where(ModelEvaluation.id == eval_record.id))
                current = result.scalar_one()
                current.status = "FAILED"
                current.error_message = error_message[:2000]
                current.duration_ms = duration_ms
                await db.flush()

            await _retry_write(db, _mark_failed)
            await db.commit()
            await record_llm_call_in_new_session(
                model=model,
                request_model=resolved_model,
                scene=f"evaluation:{req.prompt_type}",
                status="FAILED",
                duration_ms=duration_ms,
                error_message=error_message,
            )

        # Rate limit between models
        await asyncio.sleep(1.5)

    return {
        "eval_run_id": eval_run_id,
        "model_count": len(models),
        "message": f"测评完成，共 {len(models)} 个模型",
    }


@router.get("/evaluations/runs")
async def list_eval_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all evaluation runs with summary stats."""
    # Get distinct run IDs with stats
    result = await db.execute(
        select(
            ModelEvaluation.eval_run_id,
            ModelEvaluation.prompt_type,
            func.count(ModelEvaluation.id).label("model_count"),
            func.min(ModelEvaluation.created_at).label("created_at"),
            func.sum(func.cast(ModelEvaluation.status == "DONE", SAInteger)).label("done_count"),
            func.sum(func.cast(ModelEvaluation.status == "FAILED", SAInteger)).label("fail_count"),
        )
        .group_by(ModelEvaluation.eval_run_id, ModelEvaluation.prompt_type)
        .order_by(desc(func.min(ModelEvaluation.created_at)))
        .limit(limit)
    )
    rows = result.all()

    return {
        "runs": [
            {
                "eval_run_id": r[0],
                "prompt_type": r[1],
                "model_count": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "done_count": r[4],
                "fail_count": r[5],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/evaluations/runs/{run_id}")
async def get_eval_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Get all evaluation results for a specific run."""
    result = await db.execute(
        select(ModelEvaluation)
        .where(ModelEvaluation.eval_run_id == run_id)
        .order_by(ModelEvaluation.model_name)
    )
    evals = result.scalars().all()

    if not evals:
        raise HTTPException(404, f"Evaluation run {run_id} not found")

    return {
        "eval_run_id": run_id,
        "prompt_type": evals[0].prompt_type,
        "results": [
            {
                "id": e.id,
                "model_id": e.model_id,
                "model_name": e.model_name,
                "status": e.status,
                "response_text": e.response_text,
                "duration_ms": e.duration_ms,
                "tokens_input": e.tokens_input,
                "tokens_output": e.tokens_output,
                "quality_score": e.quality_score,
                "auto_score": e.auto_score,
                "notes": e.notes,
                "error_message": e.error_message,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in evals
        ],
    }


@router.put("/evaluations/{eval_id}/score")
async def score_evaluation(
    eval_id: int,
    req: ScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """Human-score a single evaluation result."""
    result = await db.execute(
        select(ModelEvaluation).where(ModelEvaluation.id == eval_id)
    )
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(404, f"Evaluation {eval_id} not found")

    evaluation.quality_score = req.quality_score
    if req.notes:
        evaluation.notes = req.notes
    await db.commit()
    return {"message": "评分已保存"}
