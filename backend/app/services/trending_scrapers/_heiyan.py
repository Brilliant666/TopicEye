"""黑岩书城榜单 — https://h5.zhangwenpindu.cn/

源: 黑岩网（掌文品读）H5 书城的公开 CDN API。
- 接口域名: biz.zhangwenpindu.cn
- 鉴权: 无（自定义客户端头是 UA 指纹，httpx 直发即可）
- 暴露端点:
    GET /book/cdn/home?pageId=1663471786814947329     # 书城首页 (5 个 shelves)
    GET /book/cdn/shelf/page?shelfId=...&pageNo=...   # 单榜单分页 (每页 6 条)
- 失败模式:
    * 反爬: 自定义头缺失 → code=90001「业务渠道不存在」(实测)
    * 列表类目: shelfId 是硬编码常量 (artemis_heiyan_recommendation_*),
      平台改版后失效, 届时 fail-fast 即可, 不要默默写空盘.
    * 详情/章节: 需 udid, 这里**不抓** (plan 范围外).
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Set

import httpx
from . import BaseTrendingScraper, register_trending, TrendingEntry

logger = logging.getLogger(__name__)


@register_trending("heiyan")
class HeiyanTrending(BaseTrendingScraper):
    SOURCE = "heiyan"
    CATEGORY = "webnovel"

    BASE = "https://biz.zhangwenpindu.cn"
    HOME_PAGE_ID = "1663471786814947329"
    PAGE_SIZE = 20           # /shelf/page 单页条数 (实测)
    MAX_PAGES_PER_SHELF = 10  # 防失控, 单榜单最多翻 10 页 (200 本)
    THROTTLE_SECONDS = 0.2

    HEADERS = {
        "referer": "https://h5.zhangwenpindu.cn/",
        "app-name": "3",
        "client-platform": "2",
        "lang": "zh_CN",
        "app-version": "1.2.9",
        "package-time": "1736152412573",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }

    # (shelfId, 显示名). 来自书城首页 pageId=1663471786814947329 实时发现.
    SHELVES = [
        ("artemis_heiyan_recommendation_banner", "书城轮播图"),
        ("artemis_heiyan_recommendation_hot", "爆款力荐"),
        ("artemis_heiyan_recommendation_excellent", "热门绝佳"),
        ("artemis_heiyan_recommendation_new", "新书尝鲜"),
        ("artemis_heiyan_recommendation_good", "好书共赏"),
    ]

    async def fetch(self, client: httpx.AsyncClient) -> List[TrendingEntry]:
        results: List[TrendingEntry] = []
        seen: Set[str] = set()  # bookId 去重, 同本书在多个 shelf 时只入一次

        for shelf_id, shelf_label in self.SHELVES:
            shelf_entries = await self._fetch_shelf(client, shelf_id, shelf_label, seen)
            results.extend(shelf_entries)
            await asyncio.sleep(self.THROTTLE_SECONDS)

        logger.info("heiyan trending: fetched %d unique books across %d shelves",
                    len(results), len(self.SHELVES))
        return results

    async def _fetch_shelf(
        self,
        client: httpx.AsyncClient,
        shelf_id: str,
        shelf_label: str,
        seen: Set[str],
    ) -> List[TrendingEntry]:
        """抓取单个榜单全量 (分页). 失败 → []. 单页 0 条立即停."""
        entries: List[TrendingEntry] = []
        shelf_rank = 0  # 跨 shelf 的全局序号用于 hot_value

        for page in range(1, self.MAX_PAGES_PER_SHELF + 1):
            url = (
                f"{self.BASE}/book/cdn/shelf/page"
                f"?shelfId={shelf_id}&pageNo={page}&pageSize={self.PAGE_SIZE}"
            )
            try:
                resp = await client.get(url, headers=self.HEADERS, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                logger.warning("heiyan shelf %s page %d fetch failed: %s",
                               shelf_id, page, exc)
                return entries  # 已抓的保留, 后续 page 跳过

            if not payload.get("success") or payload.get("code") != 1:
                logger.warning("heiyan shelf %s page %d: code=%s msg=%s",
                               shelf_id, page, payload.get("code"), payload.get("message"))
                return entries

            data = payload.get("data") or {}
            records = data.get("records") or []
            if not records:
                # 翻到末页, 自然终止
                break

            for record in records:
                book = record.get("book") or {}
                book_id = str(book.get("id") or "").strip()
                if not book_id or book_id in seen:
                    continue
                seen.add(book_id)

                name = (book.get("name") or "").strip()
                if not name:
                    continue

                shelf_rank += 1
                author_obj = book.get("author") or {}
                intro = book.get("introduce") or ""
                if len(intro) > 200:
                    intro = intro[:200] + "…"

                tags_raw = book.get("tags") or ""
                if isinstance(tags_raw, list):
                    tags = [str(t).strip() for t in tags_raw if t]
                else:
                    tags = [t.strip() for t in str(tags_raw).replace("，", ",").split(",") if t.strip()]

                entries.append({
                    "title": name,
                    "rank": shelf_rank,
                    # hot_value 用 1/rank 风格不直观 (整数除法丢精度),
                    # 用 1000 - rank 让排在前面的数字更大, 适配前端默认排序
                    "hot_value": max(1, 1000 - shelf_rank),
                    "url": f"https://h5.zhangwenpindu.cn/#/book/{book_id}",
                    "hot_value_raw": shelf_label,
                    "trend": "stable",
                    "cover_url": book.get("iconUrlMedium") or book.get("iconUrl") or "",
                    "extra": {
                        "platform": "heiyan",
                        "book_id": book_id,
                        "author_id": str(author_obj.get("id") or ""),
                        "author": author_obj.get("name", ""),
                        "author_avatar": author_obj.get("iconUrlSmall", ""),
                        "intro": intro,
                        "words": book.get("words"),
                        "words_str": book.get("wordsStr", ""),
                        "tags": tags,
                        "finished": bool(book.get("finished")),
                        "free": bool(book.get("free")),
                        "open": bool(book.get("open")),
                        "type": book.get("type"),  # 1=短篇 3=长篇 (实测)
                        "wx_book_id": book.get("wxBookId", ""),
                        "tk_book_id": book.get("tkBookId", ""),
                        "shelf": shelf_label,
                        "shelf_id": shelf_id,
                    },
                })

            # 真实 total 在第 1 页能拿到; 如果 records < pageSize 说明末页
            total = data.get("total")
            if total is not None and shelf_rank >= int(total):
                break

            await asyncio.sleep(self.THROTTLE_SECONDS)

        return entries
