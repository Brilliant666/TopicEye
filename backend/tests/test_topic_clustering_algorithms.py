import asyncio

import pytest

from app.services import semantic_dedup, topic_clustering


@pytest.mark.asyncio
async def test_semantic_dedup_ignores_pairs_outside_current_batch(monkeypatch):
    async def fake_llm_json(*args, **kwargs):
        return {
            "duplicates": [
                [1, 2],
                [1, 999],
                [888, 2],
            ]
        }

    monkeypatch.setattr(semantic_dedup, "call_llm_json", fake_llm_json)

    result = await semantic_dedup._dedup_one_batch([
        {"id": 1, "title": "canonical", "curation_score": 80},
        {"id": 2, "title": "duplicate", "curation_score": 60},
    ])

    assert result == {2: 1}


@pytest.mark.asyncio
async def test_semantic_dedup_runs_batches_with_bounded_concurrency(monkeypatch):
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def fake_dedup_one_batch(items):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1
        return {items[1]["id"]: items[0]["id"]}

    monkeypatch.setattr(semantic_dedup, "BATCH_SIZE", 2)
    monkeypatch.setattr(semantic_dedup, "SEMANTIC_DEDUP_CONCURRENCY", 2)
    monkeypatch.setattr(semantic_dedup, "_dedup_one_batch", fake_dedup_one_batch)

    items = [
        {"id": item_id, "title": f"item {item_id}", "curation_score": 50}
        for item_id in range(1, 9)
    ]

    result = await semantic_dedup.semantic_dedup(items)

    assert result == {2: 1, 4: 3, 6: 5, 8: 7}
    assert max_active == 2


@pytest.mark.asyncio
async def test_cluster_helpers_name_and_dedup_candidate_clusters(monkeypatch):
    async def fake_call_llm_json(prompt, **kwargs):
        return {"name": "AI工具", "summary": "工具更新"}

    async def fake_semantic_dedup(items):
        return {items[1]["id"]: items[0]["id"]}

    monkeypatch.setattr(topic_clustering, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(topic_clustering, "semantic_dedup", fake_semantic_dedup)

    clusters = [
        [
            {"id": 1, "title": "AI工具发布", "tags": ["AI", "工具"], "curation_score": 80},
            {"id": 2, "title": "AI工具上线", "tags": ["AI", "产品"], "curation_score": 70},
        ],
        [
            {"id": 3, "title": "模型更新", "tags": ["模型"], "curation_score": 75},
            {"id": 4, "title": "模型升级", "tags": ["模型"], "curation_score": 65},
        ],
    ]

    names = await topic_clustering._name_clusters(clusters)
    dedup = await topic_clustering._dedup_candidate_clusters(clusters)

    assert [item["name"] for item in names] == ["AI工具", "AI工具"]
    assert [item["content_count"] for item in names] == [2, 2]
    assert dedup == {2: 1, 4: 3}
