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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, Integer as SAInteger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.llm_model import LlmModel, ModelEvaluation
from app.services.llm.model_resolver import resolve_litellm_model

router = APIRouter(prefix="/models", tags=["models"])


def _resolve_litellm_model(model: LlmModel) -> str:
    return resolve_litellm_model(model)


def _missing_explicit_api_key(model: LlmModel) -> bool:
    """OpenAI-compatible custom endpoints need an explicit key in this app."""
    return bool(model.api_base) and not bool(model.api_key)


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


def _estimate_cost(
    tokens_input: Optional[int],
    tokens_output: Optional[int],
    cost_per_1k_input: Optional[float],
    cost_per_1k_output: Optional[float],
) -> float:
    input_cost = ((tokens_input or 0) / 1000) * (cost_per_1k_input or 0)
    output_cost = ((tokens_output or 0) / 1000) * (cost_per_1k_output or 0)
    return round(input_cost + output_cost, 6)


# ── Model Config CRUD ─────────────────────────────────────────────────

@router.get("")
async def list_models(db: AsyncSession = Depends(get_db)):
    """List all configured LLM models."""
    result = await db.execute(select(LlmModel).order_by(LlmModel.id))
    models = result.scalars().all()
    await _normalize_model_roles(db, models)
    return {
        "models": [
            {
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
                "extra_params": m.extra_params,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in models
        ],
        "total": len(models),
    }


@router.post("")
async def create_model(req: ModelCreateRequest, db: AsyncSession = Depends(get_db)):
    """Add a new LLM model configuration."""
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
        cost_per_1k_input=req.cost_per_1k_input,
        cost_per_1k_output=req.cost_per_1k_output,
        extra_params=req.extra_params,
    )
    db.add(model)
    await db.flush()
    await db.commit()
    return {"id": model.id, "name": model.name, "message": "模型配置创建成功"}


@router.get("/usage/summary")
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Summarize token usage and estimated cost from recorded model evaluations."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(ModelEvaluation, LlmModel)
        .join(LlmModel, ModelEvaluation.model_id == LlmModel.id, isouter=True)
        .where(ModelEvaluation.created_at >= since)
        .order_by(desc(ModelEvaluation.created_at))
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
        "estimated_cost": 0.0,
        "duration_ms": 0,
    }

    for evaluation, model in rows:
        tokens_input = evaluation.tokens_input or 0
        tokens_output = evaluation.tokens_output or 0
        estimated_cost = _estimate_cost(
            evaluation.tokens_input,
            evaluation.tokens_output,
            model.cost_per_1k_input if model else None,
            model.cost_per_1k_output if model else None,
        )
        is_done = evaluation.status == "DONE"
        is_failed = evaluation.status == "FAILED"

        totals["calls"] += 1
        totals["success_calls"] += 1 if is_done else 0
        totals["failed_calls"] += 1 if is_failed else 0
        totals["tokens_input"] += tokens_input
        totals["tokens_output"] += tokens_output
        totals["estimated_cost"] += estimated_cost
        totals["duration_ms"] += evaluation.duration_ms or 0

        model_key = evaluation.model_id
        if model_key not in by_model:
            by_model[model_key] = {
                "model_id": evaluation.model_id,
                "model_name": model.name if model else evaluation.model_name,
                "provider": model.provider if model else None,
                "calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "estimated_cost": 0.0,
                "avg_duration_ms": 0,
                "cost_per_1k_input": model.cost_per_1k_input if model else None,
                "cost_per_1k_output": model.cost_per_1k_output if model else None,
            }
        model_stats = by_model[model_key]
        model_stats["calls"] += 1
        model_stats["success_calls"] += 1 if is_done else 0
        model_stats["failed_calls"] += 1 if is_failed else 0
        model_stats["tokens_input"] += tokens_input
        model_stats["tokens_output"] += tokens_output
        model_stats["estimated_cost"] += estimated_cost
        model_stats["avg_duration_ms"] += evaluation.duration_ms or 0

        prompt_key = evaluation.prompt_type
        if prompt_key not in by_prompt:
            by_prompt[prompt_key] = {
                "prompt_type": prompt_key,
                "calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "estimated_cost": 0.0,
            }
        prompt_stats = by_prompt[prompt_key]
        prompt_stats["calls"] += 1
        prompt_stats["success_calls"] += 1 if is_done else 0
        prompt_stats["failed_calls"] += 1 if is_failed else 0
        prompt_stats["tokens_input"] += tokens_input
        prompt_stats["tokens_output"] += tokens_output
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
    result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, f"Model {model_id} not found")

    update_data = req.model_dump(exclude_unset=True)
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

    await db.commit()
    return {"message": f"模型 {model.name} 更新成功"}


@router.delete("/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a model configuration."""
    result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, f"Model {model_id} not found")
    await db.delete(model)
    await db.commit()
    return {"message": f"模型 {model.name} 已删除"}


@router.post("/{model_id}/set-primary")
async def set_primary(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the primary model (unset others)."""
    result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, f"Model {model_id} not found")

    # Unset all others
    await db.execute(
        LlmModel.__table__.update().values(is_primary=False)
    )
    model.is_primary = True
    model.is_fallback = False
    model.enabled = True
    await db.commit()
    return {"message": f"{model.name} 已设为主模型"}


@router.post("/{model_id}/set-fallback")
async def set_fallback(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the fallback model."""
    result = await db.execute(select(LlmModel).where(LlmModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, f"Model {model_id} not found")

    await db.execute(
        LlmModel.__table__.update().values(is_fallback=False)
    )
    model.is_fallback = True
    model.is_primary = False
    model.enabled = True
    await db.commit()
    return {"message": f"{model.name} 已设为备用模型"}


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
    kwargs = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": test_prompt}],
        "temperature": 0.3,
        "max_tokens": 200,
    }
    if model.api_key:
        kwargs["api_key"] = model.api_key
    if model.api_base:
        kwargs["api_base"] = model.api_base

    start = time.monotonic()
    try:
        response = await asyncio.to_thread(completion, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)
        content = response.choices[0].message.content or ""
        usage = response.usage
        return {
            "status": "success",
            "model_name": model.name,
            "response": content,
            "duration_ms": duration_ms,
            "tokens_input": usage.prompt_tokens if usage else None,
            "tokens_output": usage.completion_tokens if usage else None,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
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
    models = result.scalars().all()
    if not models:
        raise HTTPException(400, "没有找到启用的模型")

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

    # Run each model sequentially (avoid rate limits)
    for model, eval_record in evaluations:
        eval_record.status = "RUNNING"
        await db.flush()

        if _missing_explicit_api_key(model):
            eval_record.status = "FAILED"
            eval_record.error_message = "模型配置缺少 API Key，请在模型配置中补充后再测评。"
            await asyncio.sleep(0.1)
            continue

        resolved_model = _resolve_litellm_model(model)

        kwargs = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt_text}],
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
        }
        if model.api_key:
            kwargs["api_key"] = model.api_key
        if model.api_base:
            kwargs["api_base"] = model.api_base

        start = time.monotonic()
        try:
            response = await asyncio.to_thread(completion, **kwargs)
            duration_ms = int((time.monotonic() - start) * 1000)
            content = response.choices[0].message.content or ""
            usage = response.usage

            eval_record.status = "DONE"
            eval_record.response_text = content
            eval_record.duration_ms = duration_ms
            eval_record.tokens_input = usage.prompt_tokens if usage else None
            eval_record.tokens_output = usage.completion_tokens if usage else None

            eval_record.auto_score = _auto_score_response(content)

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            eval_record.status = "FAILED"
            eval_record.error_message = str(e)[:2000]
            eval_record.duration_ms = duration_ms

        # Rate limit between models
        await asyncio.sleep(1.5)

    await db.commit()

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
