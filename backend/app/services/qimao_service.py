"""
七猫小说爬虫服务。
使用 Playwright 浏览器提取 window.__NUXT__ 数据。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Literal

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.qimao import QimaoBook
from app.services.qimao_scraper import fetch_list_data

logger = logging.getLogger(__name__)


def _parse_book(item: dict, channel: str, rank_type: str, position: int) -> dict:
    """将原始字段映射为 QimaoBook 字段。"""
    # 处理收藏数 "143.0万" -> int
    collect_count: int | None = None
    number_str = str(item.get("number", ""))
    if number_str and item.get("unit") == "万":
        try:
            collect_count = int(float(number_str) * 10000)
        except ValueError:
            pass

    return {
        "book_id": str(item.get("book_id", "")),
        "title": item.get("title", ""),
        "author": item.get("author", ""),
        "abstract": item.get("intro", ""),
        "category1_name": item.get("category1_name", ""),
        "category2_name": item.get("category2_name", ""),
        "thumb_uri": item.get("image_link", ""),
        "words_num": item.get("words_num", ""),
        "collect_count": collect_count,
        "latest_chapter_id": str(item.get("latest_chapter_id", "")),
        "latest_chapter_title": item.get("latest_chapter_title", ""),
        "update_time": item.get("update_time", ""),
        "status": int(item.get("status", 0) or 0),
        "is_over": int(item.get("is_over", 0) or 0),
        "is_new": int(item.get("is_new", 0) or 0),
        "is_continue_top": int(item.get("is_continue_top", 0) or 0),
        "index_change": int(item.get("index_change", 0) or 0),
        "surge_rank": int(item.get("surge_rank", 0) or 0),
        "bonus": int(item.get("bonus", 0) or 0),
        "channel": channel,
        "rank_type": rank_type,
        "date_type": "",
        "position": position,
    }


async def sync_qimao_ranks() -> dict:
    """
    同步七猫全量榜单：
    - 男女各 5 种榜单类型（大热/新书/完结/收藏/更新）
    - 每次请求间隔 3s
    """
    configs = [
        ("boy", "hot"), ("boy", "new"), ("boy", "over"), ("boy", "collect"), ("boy", "update"),
        ("girl", "hot"), ("girl", "new"), ("girl", "over"), ("girl", "collect"), ("girl", "update"),
    ]

    start = datetime.now()
    total_books = 0
    errors = 0

    async with async_session() as db:
        for idx, (channel, rank_type) in enumerate(configs):
            if idx > 0:
                await asyncio.sleep(3)

            books_raw = await fetch_list_data(channel, rank_type)
            if not books_raw:
                errors += 1
                logger.warning(f"七猫 {channel}/{rank_type} 获取失败")
                continue

            # 删除旧数据
            await db.execute(
                delete(QimaoBook).where(
                    QimaoBook.channel == channel,
                    QimaoBook.rank_type == rank_type,
                )
            )

            for pos, item in enumerate(books_raw, start=1):
                parsed = _parse_book(item, channel, rank_type, pos)
                db.add(QimaoBook(**parsed))

            logger.info(f"七猫 {channel}/{rank_type} 写入 {len(books_raw)} 本")
            total_books += len(books_raw)

        await db.commit()

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"=== 七猫同步完成，{total_books} 本，耗时 {elapsed:.1f}s，错误 {errors} 次 ===")

    # 通知
    try:
        from app.services.notification_service import push_notification
        await push_notification(
            "success" if errors == 0 else "warning",
            "qimao_sync",
            "七猫数据同步完成",
            f"5种榜单×男女双频，共 {total_books} 本，耗时 {elapsed:.0f}s",
        )
    except Exception:
        pass

    return {"books": total_books, "elapsed_seconds": elapsed, "errors": errors}


def run_sync() -> dict:
    """供 scheduler 调用的同步入口。"""
    return asyncio.run(sync_qimao_ranks())