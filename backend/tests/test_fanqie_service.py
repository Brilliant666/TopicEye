from types import SimpleNamespace

from app.services.fanqie_service import _refresh_book_metadata


def test_refresh_book_metadata_updates_expiring_cover_url():
    book = SimpleNamespace(
        book_name="旧书名",
        author="旧作者",
        abstract="旧简介",
        category_id="old",
        category_name="旧分类",
        thumb_uri="https://old.example/cover.image?x-expires=1",
        read_count="10",
        word_number="1000",
        last_chapter_title="旧章节",
        last_chapter_update_time=1,
    )

    _refresh_book_metadata(
        book,
        {
            "bookName": "新书名",
            "author": "新作者",
            "abstract": "新简介",
            "thumbUri": "https://new.example/cover.image?x-expires=9999999999",
            "read_count": 20,
            "wordNumber": 2000,
            "lastChapterTitle": "新章节",
            "lastChapterUpdateTime": 2,
        },
        {"category_id": "new", "category_name": "新分类"},
    )

    assert book.book_name == "新书名"
    assert book.thumb_uri == "https://new.example/cover.image?x-expires=9999999999"
    assert book.category_id == "old"
    assert book.category_name == "旧分类"
    assert book.read_count == "20"
    assert book.word_number == "2000"
