from app.main import should_retry_stats_warmup


def test_should_retry_stats_warmup_only_after_stats_failure():
    assert should_retry_stats_warmup([]) is False
    assert should_retry_stats_warmup(["scoring-flow:timeout"]) is False
    assert should_retry_stats_warmup(["stats:DuckDB analytical layer unavailable"]) is True
    assert should_retry_stats_warmup(["sources:error", "stats:attach failed"]) is True
