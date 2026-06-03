from __future__ import annotations

from app.models.source import Source, SourceStatus, SourceType
from app.services.content_pipeline import _build_http_client_kwargs, _update_source_error


def test_update_source_error_uses_readable_fallback_for_blank_message():
    source = Source(
        name="Broken API",
        url="https://example.com/api/news",
        source_type=SourceType.API,
    )

    _update_source_error(source, "")

    assert source.status == SourceStatus.ERROR
    assert source.sync_error == "信源同步失败"
    assert source.last_sync_at is not None


def test_build_http_client_kwargs_skips_explicit_proxy_for_loopback(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")

    local_kwargs = _build_http_client_kwargs("http://127.0.0.1:8999/api/news")
    remote_kwargs = _build_http_client_kwargs("https://example.com/api/news")

    assert local_kwargs["trust_env"] is False
    assert "proxy" not in local_kwargs
    assert remote_kwargs["trust_env"] is False
    assert remote_kwargs["proxy"] == "http://127.0.0.1:7890"
