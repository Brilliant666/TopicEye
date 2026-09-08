from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import rardar_news_quickread as quickread


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
async def test_network_material_failure_keeps_title_only_without_inventing_body(monkeypatch, error):
    reader = AsyncMock(side_effect=error("unavailable"))
    monkeypatch.setattr(quickread, "read_or_create_snapshot", reader)
    item = SimpleNamespace(title="Original reported title", summary=None, url="https://example.org/article")
    material = await quickread._load_material(None, item, "hacker-news")
    assert material.kind == "title_only"
    assert material.text is None
    assert material.digest == quickread._text_digest(item.title)
    assert "summaryZh MUST be null" in quickread._messages(item, material)[0]["content"]
    reader.assert_awaited_once()
