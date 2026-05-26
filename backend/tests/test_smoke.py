from app.services.dedup import build_hash, filter_duplicates, is_duplicate


def test_content_hash_and_duplicate_filter_are_stable():
    first_hash = build_hash("same title")
    second_hash = build_hash("same title")

    assert first_hash == second_hash
    assert is_duplicate(first_hash, {second_hash})

    unique, duplicates = filter_duplicates(
        [{"title": "alpha"}, {"title": "beta"}, {"title": "alpha"}]
    )

    assert [item["title"] for item in unique] == ["alpha", "beta"]
    assert [item["title"] for item in duplicates] == ["alpha"]
