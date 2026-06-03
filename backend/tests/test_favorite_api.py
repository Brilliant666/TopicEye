from __future__ import annotations

from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.dependencies import get_db
from app.api.v1 import favorites as favorites_api
from app.services.favorite_cache import invalidate_favorite_cache


@pytest_asyncio.fixture
async def favorites_client(monkeypatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    invalidate_favorite_cache()
    monkeypatch.setattr(favorites_api, "async_session", session_factory)

    app = FastAPI()
    app.include_router(favorites_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    invalidate_favorite_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_favorites_api_create_state_list_and_cache_invalidation(favorites_client: httpx.AsyncClient):
    created = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "fanqie:1001",
            "title": "番茄收藏样本",
            "url": "https://example.com/book/1001",
            "tags": ["爆款", "爽文"],
            "note": "先研究开篇钩子",
        },
    )
    assert created.status_code == 201
    favorite_id = created.json()["id"]

    state = await favorites_client.get("/favorites/state?target_type=book&target_keys=fanqie:1001,missing")
    assert state.status_code == 200
    assert state.headers["x-favorites-cache"] == "MISS"
    assert "x-favorites-cache-age-ms" not in state.headers
    assert state.json()["items"] == [
        {"target_key": "fanqie:1001", "is_favorited": True, "favorite_id": favorite_id},
        {"target_key": "missing", "is_favorited": False, "favorite_id": None},
    ]

    cached_state = await favorites_client.get("/favorites/state?target_type=book&target_keys=fanqie:1001,missing")
    assert cached_state.status_code == 200
    assert cached_state.headers["x-favorites-cache"] == "HIT"
    assert float(cached_state.headers["x-favorites-cache-age-ms"]) >= 0

    first_list = await favorites_client.get("/favorites?page=1&page_size=20")
    assert first_list.status_code == 200
    assert first_list.headers["x-favorites-cache"] == "MISS"
    assert "x-favorites-cache-age-ms" not in first_list.headers
    assert first_list.json()["total"] == 1

    second_list = await favorites_client.get("/favorites?page=1&page_size=20")
    assert second_list.status_code == 200
    assert second_list.headers["x-favorites-cache"] == "HIT"
    assert float(second_list.headers["x-favorites-cache-age-ms"]) >= 0

    updated = await favorites_client.patch(
        f"/favorites/{favorite_id}",
        json={"status": "researching", "note": "准备拆解前三章"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "researching"

    after_update = await favorites_client.get("/favorites?page=1&page_size=20&status=researching")
    assert after_update.status_code == 200
    assert after_update.headers["x-favorites-cache"] == "MISS"
    assert after_update.json()["items"][0]["note"] == "准备拆解前三章"

    keyword_by_note = await favorites_client.get("/favorites?page=1&page_size=20&keyword=前三章")
    assert keyword_by_note.status_code == 200
    assert keyword_by_note.json()["total"] == 1

    keyword_by_key = await favorites_client.get("/favorites?page=1&page_size=20&keyword=fanqie")
    assert keyword_by_key.status_code == 200
    assert keyword_by_key.json()["total"] == 1

    invalid_state = await favorites_client.get("/favorites/state?target_type=book&target_ids=1,not-a-number")
    assert invalid_state.status_code == 422
    assert invalid_state.json()["detail"] == "target_ids must be comma-separated integers"


@pytest.mark.asyncio
async def test_favorites_api_normalizes_text_identity_fields(favorites_client: httpx.AsyncClient):
    blank_key = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "     ",
            "title": "空白目标键样本",
        },
    )
    assert blank_key.status_code == 422
    assert "target_id or target_key is required" in str(blank_key.json()["detail"])

    created = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "  fanqie:normalized  ",
            "title": "  归一化收藏样本  ",
            "url": "  https://example.com/book/normalized  ",
            "source_name": "  番茄小说  ",
            "note": "  先看开篇  ",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["target_key"] == "fanqie:normalized"
    assert payload["title"] == "归一化收藏样本"
    assert payload["url"] == "https://example.com/book/normalized"
    assert payload["source_name"] == "番茄小说"
    assert payload["note"] == "先看开篇"

    cleared_note = await favorites_client.patch(
        f"/favorites/{payload['id']}",
        json={"note": "    "},
    )
    assert cleared_note.status_code == 200
    assert cleared_note.json()["note"] is None


@pytest.mark.asyncio
async def test_favorites_api_upsert_preserves_existing_status_without_explicit_status(
    favorites_client: httpx.AsyncClient,
):
    created = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "book:preserve-status",
            "title": "收藏状态保持样本",
            "status": "drafting",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "drafting"
    original_position = created.json()["position"]

    repeated = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "book:preserve-status",
            "title": "重复收藏不应重置状态",
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["status"] == "drafting"
    assert repeated.json()["position"] == original_position
    assert repeated.json()["title"] == "重复收藏不应重置状态"

    explicit_move = await favorites_client.post(
        "/favorites",
        json={
            "target_type": "book",
            "target_key": "book:preserve-status",
            "title": "显式移动收藏状态",
            "status": "researching",
        },
    )
    assert explicit_move.status_code == 201
    assert explicit_move.json()["status"] == "researching"
    assert explicit_move.json()["position"] == 1000


@pytest.mark.asyncio
async def test_favorites_api_reorder_persists_board_order(favorites_client: httpx.AsyncClient):
    created = []
    for key, title in [
        ("book:one", "第一本"),
        ("source:one", "一个信源"),
        ("trend:one", "一个趋势"),
    ]:
        target_type = key.split(":", 1)[0]
        response = await favorites_client.post(
            "/favorites",
            json={"target_type": target_type, "target_key": key, "title": title},
        )
        assert response.status_code == 201
        created.append(response.json())

    ordered_ids = [created[2]["id"], created[0]["id"], created[1]["id"]]
    reordered = await favorites_client.post(
        "/favorites/reorder",
        json={"status": "drafting", "ordered_ids": ordered_ids},
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()] == ordered_ids
    assert [item["position"] for item in reordered.json()] == [1000, 2000, 3000]
    assert {item["status"] for item in reordered.json()} == {"drafting"}

    listed = await favorites_client.get("/favorites?page=1&page_size=20&status=drafting")
    assert listed.status_code == 200
    payload = listed.json()
    assert [item["id"] for item in payload["items"]] == ordered_ids
    assert [item["position"] for item in payload["items"]] == [1000, 2000, 3000]


@pytest.mark.asyncio
async def test_favorites_api_reorder_normalizes_unsubmitted_status_items(favorites_client: httpx.AsyncClient):
    created = []
    for index in range(4):
        response = await favorites_client.post(
            "/favorites",
            json={
                "target_type": "book",
                "target_key": f"book:partial:{index}",
                "title": f"部分排序样本 {index}",
            },
        )
        assert response.status_code == 201
        created.append(response.json())

    ordered_ids = [created[2]["id"], created[0]["id"]]
    reordered = await favorites_client.post(
        "/favorites/reorder",
        json={"status": "inbox", "ordered_ids": ordered_ids},
    )

    assert reordered.status_code == 200
    payload = reordered.json()
    assert [item["id"] for item in payload] == [
        created[2]["id"],
        created[0]["id"],
        created[3]["id"],
        created[1]["id"],
    ]
    assert [item["position"] for item in payload] == [1000, 2000, 3000, 4000]

    listed = await favorites_client.get("/favorites?page=1&page_size=20&status=inbox")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["id"] for item in items] == [item["id"] for item in payload]
    assert [item["position"] for item in items] == [1000, 2000, 3000, 4000]


@pytest.mark.asyncio
async def test_favorites_api_reorder_persists_cross_status_drag_columns(favorites_client: httpx.AsyncClient):
    created = []
    for index in range(4):
        response = await favorites_client.post(
            "/favorites",
            json={
                "target_type": "book",
                "target_key": f"book:cross-drag:{index}",
                "title": f"跨列拖拽样本 {index}",
            },
        )
        assert response.status_code == 201
        created.append(response.json())

    draft_tail = await favorites_client.patch(
        f"/favorites/{created[3]['id']}",
        json={"status": "drafting"},
    )
    assert draft_tail.status_code == 200

    source_order = [created[0]["id"], created[1]["id"], created[2]["id"]]
    normalized_source = await favorites_client.post(
        "/favorites/reorder",
        json={"status": "inbox", "ordered_ids": source_order},
    )
    assert normalized_source.status_code == 200

    moved_id = created[1]["id"]
    target_saved = await favorites_client.post(
        "/favorites/reorder",
        json={"status": "drafting", "ordered_ids": [moved_id, created[3]["id"]]},
    )
    assert target_saved.status_code == 200
    assert [item["id"] for item in target_saved.json()] == [moved_id, created[3]["id"]]
    assert [item["position"] for item in target_saved.json()] == [1000, 2000]

    source_saved = await favorites_client.post(
        "/favorites/reorder",
        json={"status": "inbox", "ordered_ids": [created[0]["id"], created[2]["id"]]},
    )
    assert source_saved.status_code == 200
    assert [item["id"] for item in source_saved.json()] == [created[0]["id"], created[2]["id"]]
    assert [item["position"] for item in source_saved.json()] == [1000, 2000]

    listed_inbox = await favorites_client.get("/favorites?page=1&page_size=20&status=inbox")
    listed_drafting = await favorites_client.get("/favorites?page=1&page_size=20&status=drafting")
    assert listed_inbox.status_code == 200
    assert listed_drafting.status_code == 200
    assert [item["id"] for item in listed_inbox.json()["items"]] == [created[0]["id"], created[2]["id"]]
    assert [item["position"] for item in listed_inbox.json()["items"]] == [1000, 2000]
    assert [item["id"] for item in listed_drafting.json()["items"]] == [moved_id, created[3]["id"]]
    assert [item["position"] for item in listed_drafting.json()["items"]] == [1000, 2000]


@pytest.mark.asyncio
async def test_favorites_api_bulk_status_normalizes_target_column(favorites_client: httpx.AsyncClient):
    created = []
    for index in range(5):
        response = await favorites_client.post(
            "/favorites",
            json={
                "target_type": "book",
                "target_key": f"book:bulk-status:{index}",
                "title": f"批量移动样本 {index}",
            },
        )
        assert response.status_code == 201
        created.append(response.json())

    existing_tail = await favorites_client.patch(
        f"/favorites/{created[4]['id']}",
        json={"status": "researching"},
    )
    assert existing_tail.status_code == 200

    moved_ids = [created[2]["id"], created[0]["id"], created[1]["id"]]
    updated = await favorites_client.post(
        "/favorites/bulk-status",
        json={"status": "researching", "ids": moved_ids},
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert [item["id"] for item in payload] == moved_ids + [created[4]["id"]]
    assert [item["status"] for item in payload] == ["researching"] * 4
    assert [item["position"] for item in payload] == [1000, 2000, 3000, 4000]

    listed = await favorites_client.get("/favorites?page=1&page_size=20&status=researching")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["id"] for item in items] == [item["id"] for item in payload]
    assert [item["position"] for item in items] == [1000, 2000, 3000, 4000]


@pytest.mark.asyncio
async def test_favorites_api_bulk_delete_removes_selected_items(favorites_client: httpx.AsyncClient):
    created = []
    for index in range(4):
        response = await favorites_client.post(
            "/favorites",
            json={
                "target_type": "book",
                "target_key": f"book:bulk-delete:{index}",
                "title": f"批量删除样本 {index}",
            },
        )
        assert response.status_code == 201
        created.append(response.json())

    deleted_ids = [created[2]["id"], created[0]["id"]]
    deleted = await favorites_client.post(
        "/favorites/bulk-delete",
        json={"ids": deleted_ids},
    )

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 2}

    listed = await favorites_client.get("/favorites?page=1&page_size=20")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert {item["id"] for item in payload["items"]} == {created[1]["id"], created[3]["id"]}

    missing = await favorites_client.post(
        "/favorites/bulk-delete",
        json={"ids": [created[1]["id"], 999999]},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Favorite not found: 999999"
