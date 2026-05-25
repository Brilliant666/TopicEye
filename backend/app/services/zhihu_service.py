"""
知乎盐选专栏爬取服务。

数据来源：https://www.zhihu.com/xen/market/vip/remix-album
HTML 直接嵌入 categories + listData JSON，无需登录/cookie。

注意：知乎可能对无 User-Agent 的请求返回非完整数据。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.zhihu import ZhihuAlbum, ZhihuCategory, ZhihuRankSnapshot

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.zhihu.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

BASE_URL = 'https://www.zhihu.com/xen/market/vip/remix-album'

# 全部排序类型
SORT_TYPES = ['hottest', 'newest', 'monthly_hottest']
# 全部分类（story 下全部子分类单独爬）
STORY_SUBCATS = [
    ('故事', '爱情', '1513'),
    ('故事', '科幻', '1514'),
    ('故事', '历史', '1515'),
    ('故事', '漫画', '1516'),
    ('故事', '脑洞', '1517'),
    ('故事', '奇闻', '1518'),
    ('故事', '亲历', '1519'),
    ('故事', '校园', '1520'),
    ('故事', '悬疑', '1521'),
]


def extract_inline_data(html: str) -> Optional[dict]:
    """从 HTML 中解析 categories + listData 内联 JSON。"""
    # 找 categories 数组起始位置
    cats_start = html.find('"categories":')
    if cats_start < 0:
        return None

    # 向前找到根对象起点（最近的 { ）
    root_start = html.rfind('{', 0, cats_start)
    if root_start < 0:
        return None

    # 从 root_start 向后找匹配的关闭 }
    depth = 0
    end = cats_start
    i = cats_start
    while i < len(html):
        c = html[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1

    json_str = html[root_start:end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def parse_album_item(item: dict) -> dict:
    """将 API item 字典映射为数据库字段。"""
    rights = item.get('resource_rights', []) or []
    sub_right = rights[0] if rights else {}
    return {
        'business_id': str(item.get('business_id', '')),
        'title': item.get('title', '') or '',
        'author': (item.get('author') or [''])[0],
        'author_desc': item.get('author_desc'),
        'abstract': item.get('description') or item.get('summary', ''),
        'thumb_url': (item.get('image') or [None])[0] or item.get('artwork'),
        'chapter_text': item.get('chapter_text'),
        'price': item.get('price', 0) or 0,
        'original_price': item.get('original_price') or item.get('price', 0) or 0,
        'is_exclusive': item.get('tag_before_title') == '独家',
        'is_svip': item.get('svip_privileges', False),
        'is_purchased': item.get('is_purchased', False),
        'online_time': item.get('online_time'),
        'online_time_text': item.get('online_time_text'),
        'tag': item.get('tag_before_title'),
        'subscription_name': sub_right.get('subscription_name'),
        'media_type': item.get('media_type'),
        'subcategory': item.get('subcategory'),
        'business_line': item.get('business_line'),
    }


async def _fetch_page(url: str) -> Optional[str]:
    """下载单个页面 HTML。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            logger.warning(f'Zhihu fetch {url} status={resp.status_code}')
    except Exception as e:
        logger.warning(f'Zhihu fetch {url} error: {e}')
    return None


async def sync_categories() -> int:
    """拉取并保存知乎全部分类。"""
    html = await _fetch_page(BASE_URL)
    if not html:
        return 0

    data = extract_inline_data(html)
    if not data:
        return 0

    cats = data.get('categories', [])
    if not cats:
        return 0

    records = []
    for cat in cats:
        records.append({
            'zhihu_id': str(cat['id']),
            'name': cat['name'],
            'name_en': cat.get('name_en'),
            'level': cat.get('level', 1),
            'parent_id': str(cat['parent_id']) if cat.get('parent_id') else None,
            'sort': cat.get('sort', 0),
            'artwork': cat.get('artwork'),
        })
        for sub in cat.get('sub_category', []):
            records.append({
                'zhihu_id': str(sub['id']),
                'name': sub['name'],
                'name_en': sub.get('name_en'),
                'level': sub.get('level', 2),
                'parent_id': str(sub['parent_id']),
                'sort': sub.get('sort', 0),
                'artwork': sub.get('artwork'),
            })

    async with async_session() as db:
        for rec in records:
            stmt = sqlite_insert(ZhihuCategory).values(rec)
            stmt = stmt.on_conflict_do_update(
                index_elements=['zhihu_id'],
                set_=dict(
                    name=stmt.excluded.name,
                    name_en=stmt.excluded.name_en,
                    sort=stmt.excluded.sort,
                    artwork=stmt.excluded.artwork,
                )
            )
            await db.execute(stmt)
        await db.commit()

    logger.info(f'Zhihu categories saved: {len(records)}')
    return len(records)


async def _fetch_and_save_rank(
    sort_type: str,
    category1: Optional[str] = None,
    category2_id: Optional[str] = None,
    limit: int = 50,
) -> int:
    """抓取单个排序/分类组合并写入数据库。返回写入条数。"""
    # 构建 URL 参数
    params = {
        'study_type': 'album',
        'sort_type': sort_type,
        'limit': limit,
        'offset': 0,
        'dataType': 'new',
        'level': 2,
    }

    url = 'https://api.zhihu.com/market/categories/all?' + '&'.join(
        f'{k}={v}' for k, v in params.items() if v is not None
    )

    html = await _fetch_page(BASE_URL)
    if not html:
        return 0

    data = extract_inline_data(html)
    if not data:
        return 0

    list_data = data.get('listData', {})
    items = list_data.get('data', [])

    if not items:
        return 0

    # 写入数据库
    async with async_session() as db:
        for pos, item in enumerate(items, 1):
            rec = parse_album_item(item)
            rec['sort_type'] = sort_type
            rec['category1_name'] = category1 or ''
            rec['category2_name'] = category2_id or ''
            rec['position'] = pos
            rec['updated_at'] = datetime.now(timezone.utc)

            stmt = sqlite_insert(ZhihuAlbum).values(rec)
            stmt = stmt.on_conflict_do_update(
                index_elements=['business_id', 'sort_type'],
                set_=dict(
                    title=stmt.excluded.title,
                    author=stmt.excluded.author,
                    position=stmt.excluded.position,
                    rank_pos_diff=None,  # 重置，由快照计算
                    updated_at=stmt.excluded.updated_at,
                )
            )
            await db.execute(stmt)

        await db.commit()

    logger.info(f'Zhihu rank saved: {sort_type} {category1 or ""} {category2_id or ""} -> {len(items)} items')
    return len(items)


async def sync_zhihu_ranks() -> dict:
    """
    全量同步知乎榜单。
    
    策略：
    1. 先同步全部分类
    2. 再爬取 3 种排序（热门/最新/月热）× 故事分类（9 个子分类）= 27 组
    3. 全量快照存储
    
    Returns:
        {"categories": N, "rank_groups": N, "total_albums": N, "elapsed_seconds": float}
    """
    import time
    t0 = time.time()

    cat_count = await sync_categories()
    total = 0

    for _, cat2_name, cat2_id in STORY_SUBCATS:
        for sort_type in SORT_TYPES:
            n = await _fetch_and_save_rank(sort_type, cat2_name, cat2_id)
            total += n
            await asyncio.sleep(1.5)  # 避免频率限制

    elapsed = time.time() - t0
    return {
        'categories': cat_count,
        'rank_groups': len(STORY_SUBCATS) * len(SORT_TYPES),
        'total_albums': total,
        'elapsed_seconds': round(elapsed, 1),
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(sync_zhihu_ranks())
    print('Result:', result)