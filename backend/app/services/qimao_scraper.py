"""
七猫小说爬虫 - 使用 Playwright 浏览器提取 window.__NUXT__ 数据。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

BASE_URL = "https://www.qimao.com/paihang"

# Proxy from environment
PROXY_URL = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or ""


def _get_proxy_settings():
    """Return playwright proxy dict if proxy is configured."""
    if PROXY_URL:
        return {"server": PROXY_URL}
    return None


async def fetch_list_data(channel: str, rank_type: str) -> list[dict] | None:
    """用 Playwright 打开页面，等待 NUXT 数据注入，返回 listData。"""
    url = f"{BASE_URL}/{channel}/{rank_type}/"
    proxy = _get_proxy_settings()
    try:
        async with async_playwright() as pw:
            launch_args = {"headless": True}
            if proxy:
                launch_args["proxy"] = proxy
            browser = await pw.chromium.launch(**launch_args)
            try:
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
                return list_data
            finally:
                await browser.close()
    except Exception as e:
        logger.error(f"Playwright 爬取失败 {channel}/{rank_type}: {e}")
        return None


async def fetch_all_ranks() -> dict[tuple[str, str], list[dict]]:
    """
    一次性启动浏览器，逐个爬取 10 个榜单。
    返回 {(channel, rank_type): [items...]} 字典。
    """
    configs = [
        ("boy", "hot"), ("boy", "new"), ("boy", "over"), ("boy", "collect"), ("boy", "update"),
        ("girl", "hot"), ("girl", "new"), ("girl", "over"), ("girl", "collect"), ("girl", "update"),
    ]

    results: dict[tuple[str, str], list[dict]] = {}
    proxy = _get_proxy_settings()

    async with async_playwright() as pw:
        launch_args = {"headless": True}
        if proxy:
            launch_args["proxy"] = proxy
        browser = await pw.chromium.launch(**launch_args)

        try:
            for idx, (channel, rank_type) in enumerate(configs):
                if idx > 0:
                    await asyncio.sleep(1.5)

                url = f"{BASE_URL}/{channel}/{rank_type}/"
                try:
                    page = await browser.new_page()
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=15000)

                        list_data = await page.evaluate("""
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

                        if list_data:
                            results[(channel, rank_type)] = list_data
                            logger.info(f"七猫 {channel}/{rank_type} 获取 {len(list_data)} 本")
                        else:
                            results[(channel, rank_type)] = []
                            logger.warning(f"七猫 {channel}/{rank_type} 无 listData")
                    finally:
                        await page.close()
                except Exception as e:
                    results[(channel, rank_type)] = []
                    logger.error(f"七猫 {channel}/{rank_type} 爬取失败: {e}")
        finally:
            await browser.close()

    return results
