"""点众阅读榜单 — https://www.ishugui.com/

源: 点众网（ishugui）PC 站 Next.js SSG 的公开数据端点。
- 接口域名: www.ishugui.com/_next/data/{build_id}/
- 鉴权: 无 (普通 GET, 标准浏览器 UA 即可)
- 暴露端点 (实测):
    GET /index.json                          # 首页 (banner + 男女榜 + 热销)
    GET /ranking/1-1.json?types=1-1          # 男生榜
    GET /ranking/1-3.json?types=1-3          # 女生榜
    GET /book/{bookId}.json                  # 详情 (含首章正文, plan 范围外, 暂不用)
- 失败模式:
    * build_id (`dzread_20250428`) 是构建时常量, 新版会失效.
      自动从首页 HTML 探测, 失败回退到 KNOWN_BUILD_ID.
    * 榜单 types 是数字约定 (1-1=男生/1-3=女生), 平台改版后需重新发现.
    * book 详情有首章正文 (`chapterInfo.content`); 付费章节 (`isCharge=1`)
      拿不到正文 —— 不强行抓, 符合"扫榜"定位.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Set, Tuple

import httpx
from . import BaseTrendingScraper, register_trending, TrendingEntry

logger = logging.getLogger(__name__)

# Next.js SSG 把 build_id 嵌在 _next/data/ 路径里. 兜底用.
_BUILD_ID_RE = re.compile(r"/_next/data/([A-Za-z0-9_]+)/")


@register_trending("ishugui")
class IshuguiTrending(BaseTrendingScraper):
    SOURCE = "ishugui"
    CATEGORY = "webnovel"

    BASE_DATA = "https://www.ishugui.com/_next/data"
    INDEX_URL = "https://www.ishugui.com/"
    KNOWN_BUILD_ID = "dzread_20250428"  # 兜底值; 探测失败时使用
    THROTTLE_SECONDS = 0.2

    # (types 路径段, 显示名, 性别标签)
    RANKING_ENDPOINTS = [
        ("1-1", "男生榜", "male"),
        ("1-3", "女生榜", "female"),
    ]

    HEADERS = {
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": "https://www.ishugui.com/",
    }

    # ── Entry points ───────────────────────────────────────────────
    async def fetch(self, client: httpx.AsyncClient) -> List[TrendingEntry]:
        build_id = await self._discover_build_id(client)
        logger.info("ishugui trending: using build_id=%s", build_id)

        results: List[TrendingEntry] = []
        seen: Set[str] = set()

        # 1) 首页: 拿 banner + seoColumnVos (含热销/完本/新书等)
        index_entries = await self._fetch_index(client, build_id, seen)
        results.extend(index_entries)
        await asyncio.sleep(self.THROTTLE_SECONDS)

        # 2) 男女频分榜单: 每类可能含多个 rankVos
        for types_path, label, gender in self.RANKING_ENDPOINTS:
            rank_entries = await self._fetch_ranking(client, build_id, types_path, label, gender, seen)
            results.extend(rank_entries)
            await asyncio.sleep(self.THROTTLE_SECONDS)

        logger.info("ishugui trending: fetched %d unique books (build_id=%s)",
                    len(results), build_id)
        return results

    # ── Build ID discovery ────────────────────────────────────────
    async def _discover_build_id(self, client: httpx.AsyncClient) -> str:
        """从首页 HTML 抓 _next/data/{id}/ 里的 build id. 失败 → 兜底."""
        try:
            resp = await client.get(self.INDEX_URL, headers=self.HEADERS, timeout=20)
            resp.raise_for_status()
            m = _BUILD_ID_RE.search(resp.text)
            if m:
                return m.group(1)
            logger.warning("ishugui: build_id regex miss, falling back")
        except Exception as exc:
            logger.warning("ishugui: build_id discovery failed: %s", exc)
        return self.KNOWN_BUILD_ID

    # ── Index page (banner + seoColumnVos) ───────────────────────
    async def _fetch_index(
        self,
        client: httpx.AsyncClient,
        build_id: str,
        seen: Set[str],
    ) -> List[TrendingEntry]:
        url = f"{self.BASE_DATA}/{build_id}/index.json"
        try:
            resp = await client.get(url, headers=self.HEADERS, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("ishugui index fetch failed: %s", exc)
            return []

        page_props = payload.get("pageProps") or {}
        entries: List[TrendingEntry] = []
        global_rank = 0

        # seoColumnVos: 三级分类榜单. 每个 vo 里有 rankVos, 每个 rankVo 里有 bookInfos
        for col in page_props.get("seoColumnVos", []):
            col_code = col.get("code", "")
            col_label = "首页榜单"
            for mgmt in col.get("seoColumnManageVos", []):
                mgmt_name = mgmt.get("name", "")
                for rank in mgmt.get("rankVos", []):
                    rank_name = rank.get("rankName", mgmt_name)
                    for idx, info in enumerate(rank.get("bookInfos", []), start=1):
                        global_rank += 1
                        entry = self._build_entry(
                            info, f"首页/{col_label}/{mgmt_name}/{rank_name}",
                            global_rank, rank_name,
                        )
                        if entry and entry["extra"]["book_id"] not in seen:
                            seen.add(entry["extra"]["book_id"])
                            entries.append(entry)

        # bannerList: 头部轮播 (少而精, 通常 2-3 本)
        for banner in page_props.get("bannerList", []):
            book_id = str(banner.get("bookId") or "")
            if not book_id or book_id in seen:
                continue
            # banner 字段比 book 字段少, 用最少的子集构造
            global_rank += 1
            seen.add(book_id)
            entries.append({
                "title": (banner.get("name") or "").strip(),
                "rank": global_rank,
                "hot_value": max(1, 1000 - global_rank),
                "url": f"https://www.ishugui.com/book/{book_id}.html",
                "hot_value_raw": "首页 banner",
                "trend": "stable",
                "cover_url": banner.get("pcUrl") or banner.get("wapUrl") or "",
                "extra": {
                    "platform": "ishugui",
                    "book_id": book_id,
                    "shelf": "首页 banner",
                    "shelf_id": "banner",
                },
            })

        return entries

    # ── Ranking endpoints (male / female) ─────────────────────────
    async def _fetch_ranking(
        self,
        client: httpx.AsyncClient,
        build_id: str,
        types_path: str,
        label: str,
        gender: str,
        seen: Set[str],
    ) -> List[TrendingEntry]:
        url = f"{self.BASE_DATA}/{build_id}/ranking/{types_path}.json?types={types_path}"
        try:
            resp = await client.get(url, headers=self.HEADERS, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("ishugui ranking %s fetch failed: %s", types_path, exc)
            return []

        page_props = payload.get("pageProps") or {}
        entries: List[TrendingEntry] = []

        # rankData 列出这个榜单下有哪些子榜单 (日榜/月榜, rankStyle "1,2")
        # rankBook 是实际的书列表 (单页, 不分页)
        # 当前实现: 取第 1 个子榜单的 bookInfos (实测评测 1-1/1-3 各只 1 个 rankVo 30 本)
        rank_datas = page_props.get("rankData") or []
        if not rank_datas:
            logger.warning("ishugui ranking %s: empty rankData", types_path)
            return []

        for rd in rank_datas:
            for sub in rd.get("subList", []):
                sub_code = sub.get("code")
                sub_name = sub.get("name", "")
                if not sub_code:
                    continue
                # rankBook 字段是当前榜单的 books
                rank_books = page_props.get("rankBook") or []
                for idx, info in enumerate(rank_books, start=1):
                    entry = self._build_entry(
                        info, f"{label}/{sub_name}", idx, sub_name,
                    )
                    if entry and entry["extra"]["book_id"] not in seen:
                        seen.add(entry["extra"]["book_id"])
                        entries.append(entry)

        return entries

    # ── Entry builder ─────────────────────────────────────────────
    def _build_entry(
        self,
        info: dict,
        shelf_label: str,
        rank: int,
        rank_name: str,
    ) -> Optional[TrendingEntry]:
        """从 ishugui book info 构造 TrendingEntry. 字段不全则跳过."""
        book_id = str(info.get("bookId") or "").strip()
        if not book_id:
            return None
        name = (info.get("bookName") or "").strip()
        if not name:
            return None

        author = (info.get("author") or "").strip()
        intro = (info.get("introduction") or "").strip()
        if len(intro) > 200:
            intro = intro[:200] + "…"

        # tagV3 是数组; bookTypeList 是分类; status/statusCn 是状态
        tags = info.get("tagV3") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()]

        book_type_list = info.get("bookTypeList") or []
        one_type = book_type_list[0].get("oneTypeName", "") if book_type_list else ""

        return {
            "title": name,
            "rank": rank,
            "hot_value": max(1, 1000 - rank),
            "url": f"https://www.ishugui.com/book/{book_id}.html",
            "hot_value_raw": rank_name or shelf_label,
            "trend": "stable",
            "cover_url": info.get("coverWap", ""),
            "extra": {
                "platform": "ishugui",
                "book_id": book_id,
                "author": author,
                "intro": intro,
                "cover_url": info.get("coverWap", ""),
                "total_word_size": info.get("totalWordSize", ""),
                "total_chapter_num": info.get("totalChapterNum"),
                "last_chapter_name": info.get("lastChapterName", ""),
                "last_chapter_utime": info.get("lastChapterUtime", ""),
                "click_num": info.get("clickNum", ""),
                "status": info.get("status"),  # 1=完本/连载 (待映射)
                "status_cn": info.get("statusCn", ""),
                "book_score": info.get("scoreNum") or info.get("bookScore"),
                "tag_v3": tags,
                "book_type_list": book_type_list,
                "one_type": one_type,
                "shelf": shelf_label,
                "rank_name": rank_name,
            },
        }
