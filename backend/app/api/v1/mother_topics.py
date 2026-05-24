"""
母题相关 API。
提供母题的 CRUD、关键词打分、内容匹配接口。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.mother_topic import MotherTopic, ContentType
from app.models.content import ContentItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mother-topics", tags=["母题"])


# ── Pydantic 请求/响应模型 ─────────────────────────────────────────────

class MotherTopicBase(BaseModel):
    name: str
    description: Optional[str] = None
    keywords: list[str] = []
    weight: float = 1.0
    content_type: Optional[str] = None
    target_reader: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


class MotherTopicCreate(MotherTopicBase):
    pass


class MotherTopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    weight: Optional[float] = None
    content_type: Optional[str] = None
    target_reader: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class MotherTopicOut(MotherTopicBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, obj) -> "MotherTopicOut":
        """Convert SQLAlchemy model to dict, serializing datetimes."""
        d = {
            "id": obj.id,
            "name": obj.name,
            "description": obj.description,
            "keywords": obj.keywords,
            "weight": obj.weight,
            "content_type": obj.content_type,
            "target_reader": obj.target_reader,
            "is_active": obj.is_active,
            "display_order": obj.display_order,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        }
        return cls(**d)


class ContentScoringRequest(BaseModel):
    title: str
    summary: Optional[str] = ""
    source: Optional[str] = None
    hot_value: int = 0


class ContentScoringResult(BaseModel):
    title: str
    topic_scores: list[dict]  # [{name, score, weight, final}]
    top_topic: Optional[str]
    final_score: float


# ── 路由 ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[MotherTopicOut])
async def list_mother_topics(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """列出所有母题，支持只返回激活的。"""
    stmt = select(MotherTopic).order_by(MotherTopic.display_order, MotherTopic.id)
    if active_only:
        stmt = stmt.where(MotherTopic.is_active == True)
    result = await db.execute(stmt)
    topics = result.scalars().all()
    return [MotherTopicOut.from_orm_model(t) for t in topics]


@router.post("/", response_model=MotherTopicOut)
async def create_mother_topic(
    topic_in: MotherTopicCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建新母题。"""
    topic = MotherTopic(
        name=topic_in.name,
        description=topic_in.description,
        keywords=topic_in.keywords,
        weight=topic_in.weight,
        content_type=topic_in.content_type,
        target_reader=topic_in.target_reader,
        is_active=topic_in.is_active,
        display_order=topic_in.display_order,
    )
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return MotherTopicOut.from_orm_model(topic)


@router.put("/{topic_id}", response_model=MotherTopicOut)
async def update_mother_topic(
    topic_id: int,
    update_in: MotherTopicUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新母题。"""
    topic = await db.get(MotherTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="母题不存在")
    for field, value in update_in.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(topic, field, value)
    await db.commit()
    await db.refresh(topic)
    return MotherTopicOut.from_orm_model(topic)


@router.delete("/{topic_id}")
async def delete_mother_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除母题（软删除：is_active=False）。"""
    topic = await db.get(MotherTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="母题不存在")
    topic.is_active = False
    await db.commit()
    return {"ok": True, "message": "母题已停用"}


@router.post("/score", response_model=ContentScoringResult)
async def score_content(
    req: ContentScoringRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    对单条内容按母题打分。
    用于：选题候选打分、我的母题页过滤。
    """
    text = f"{req.title} {req.summary or ''}"

    # 获取激活的母题
    result = await db.execute(
        select(MotherTopic).where(MotherTopic.is_active == True).order_by(MotherTopic.display_order)
    )
    topics = result.scalars().all()

    if not topics:
        return ContentScoringResult(
            title=req.title,
            topic_scores=[],
            top_topic=None,
            final_score=0.0,
        )

    topic_scores = []
    for topic in topics:
        keyword_score = topic.match_score(text)
        # 来源新鲜度（简化：直接用 hot_value / 1000 作为基础分）
        freshness = min(1.0, req.hot_value / 10000)
        # 母题匹配分 × 权重 + 新鲜度加成（0.0 ~ 1.1）
        raw = keyword_score * topic.weight + freshness * 0.1
        # 归一化到 0-100，理论上限约 110
        final = round(min(raw * (100 / 1.1), 100), 1)
        topic_scores.append({
            "name": topic.name,
            "keyword_score": round(keyword_score, 3),
            "weight": topic.weight,
            "freshness": round(freshness, 3),
            "final": final,
        })

    # 按最终分数排序
    topic_scores.sort(key=lambda x: x["final"], reverse=True)
    top = topic_scores[0] if topic_scores else None

    final_score = top["final"] if top else 0.0

    return ContentScoringResult(
        title=req.title,
        topic_scores=topic_scores,
        top_topic=top["name"] if top else None,
        final_score=final_score,
    )


@router.get("/match/{content_id}")
async def match_content_to_topics(
    content_id: int,
    db: AsyncSession = Depends(get_db),
):
    """对已入库的内容重新匹配母题。"""
    content = await db.get(ContentItem, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="内容不存在")

    text = f"{content.title} {content.summary or ''}"

    result = await db.execute(
        select(MotherTopic).where(MotherTopic.is_active == True).order_by(MotherTopic.display_order)
    )
    topics = result.scalars().all()

    topic_scores = []
    for topic in topics:
        keyword_score = topic.match_score(text)
        final = round(keyword_score * topic.weight, 3)
        topic_scores.append({
            "name": topic.name,
            "keyword_score": round(keyword_score, 3),
            "weight": topic.weight,
            "final": final,
        })

    topic_scores.sort(key=lambda x: x["final"], reverse=True)
    top = topic_scores[0] if topic_scores else None

    return {
        "content_id": content_id,
        "title": content.title,
        "top_topic": top["name"] if top else None,
        "top_score": top["final"] if top else 0.0,
        "all_scores": topic_scores,
    }