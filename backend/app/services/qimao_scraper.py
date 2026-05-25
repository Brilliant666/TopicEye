"""
七猫小说爬虫 - 使用 Playwright 浏览器提取 window.__NUXT__ 数据。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_URL = "https://www.qimao.com/paihang"


async def fetch_list_data(channel: str, rank_type: str) -> list[dict] | None:
    """用 Playwright 打开页面，等待 NUXT 数据注入，返回 listData。"""
    url = f"{BASE_URL}/{channel}/{rank_type}/"
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=15000)

            # 从 window.__NUXT__ 中取 listData
            list_data: list[dict] | None = await page.evaluate("""
                () => {
                    try {
                        const nuxt = window.__NUXT__;
                        if (!nuxt || !nuxt.fetch) return null;
                        const keys = Object.keys(nuxt.fetch);
                        if (!keys.length) return null;
                        const firstKey = keys[0];
                        const val = nuxt.fetch[firstKey];
                        return val && val.listData ? val.listData : null;
                    } catch(e) { return null; }
                }
            """)

            await browser.close()
            return list_data
    except Exception as e:
        logger.error(f"Playwright 爬取失败 {channel}/{rank_type}: {e}")
        return None