"""Deterministic concurrency checks for the shared public-read cache."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event as ThreadEvent, Lock

import pytest

from app.integrations.rardar import read_cache


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(read_cache, "monotonic", lambda: 101.0)
    read_cache.clear()
    yield
    read_cache.clear()


def _observed_event(waiting: ThreadEvent):
    class ObservedEvent:
        def __init__(self):
            self._event = ThreadEvent()

        def wait(self, timeout=None):
            waiting.set()
            return self._event.wait(timeout)

        def set(self):
            self._event.set()

    return ObservedEvent


def test_different_keys_build_in_parallel():
    first_started = ThreadEvent()
    release_first = ThreadEvent()
    second_started = ThreadEvent()

    def first_build():
        first_started.set()
        assert release_first.wait(5)
        return "first"

    def second_build():
        second_started.set()
        return "second"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(read_cache.cached, ("first",), first_build)
        assert first_started.wait(5)
        try:
            second = pool.submit(read_cache.cached, ("second",), second_build)
            assert second_started.wait(5)
            assert second.result(timeout=5) == "second"
        finally:
            release_first.set()
        assert first.result(timeout=5) == "first"


def test_same_key_builds_once_and_returns_isolated_values():
    workers = 8
    ready = Barrier(workers)
    build_started = ThreadEvent()
    release_build = ThreadEvent()
    calls = 0
    calls_lock = Lock()

    def build():
        nonlocal calls
        with calls_lock:
            calls += 1
        build_started.set()
        assert release_build.wait(5)
        return {"items": [1]}

    def read():
        ready.wait(timeout=5)
        return read_cache.cached(("shared",), build)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(read) for _ in range(workers)]
        assert build_started.wait(5)
        release_build.set()
        results = [future.result(timeout=5) for future in futures]

    assert calls == 1
    results[0]["items"].append(2)
    assert results[1:] == [{"items": [1]}] * (workers - 1)
    assert read_cache.cached(("shared",), lambda: pytest.fail("cache miss")) == {"items": [1]}


def test_failed_build_notifies_waiters_and_does_not_block_another_key(monkeypatch):
    waiter_blocked = ThreadEvent()
    monkeypatch.setattr(read_cache, "Event", _observed_event(waiter_blocked))
    failed_started = ThreadEvent()
    release_failure = ThreadEvent()
    other_started = ThreadEvent()
    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        failed_started.set()
        assert release_failure.wait(5)
        raise ValueError("fixture failure")

    def other():
        other_started.set()
        return "other"

    with ThreadPoolExecutor(max_workers=3) as pool:
        leader = pool.submit(read_cache.cached, ("failed",), fail)
        assert failed_started.wait(5)
        waiter = pool.submit(read_cache.cached, ("failed",), fail)
        assert waiter_blocked.wait(5)
        try:
            unrelated = pool.submit(read_cache.cached, ("other",), other)
            assert other_started.wait(5)
            assert unrelated.result(timeout=5) == "other"
        finally:
            release_failure.set()

        for future in (leader, waiter):
            with pytest.raises(ValueError, match="fixture failure"):
                future.result(timeout=5)

    assert calls == 1
    assert read_cache.cached(("failed",), lambda: "recovered") == "recovered"


@pytest.mark.parametrize("blocked_stage", ["select", "deepcopy"])
def test_select_and_deepcopy_do_not_block_another_key(monkeypatch, blocked_stage):
    cached_value = {"marker": "blocked", "items": [1]}
    assert read_cache.cached(("blocked",), lambda: cached_value) == cached_value
    stage_started = ThreadEvent()
    release_stage = ThreadEvent()
    other_started = ThreadEvent()
    expected = cached_value
    kwargs = {}

    if blocked_stage == "select":

        def select(value):
            stage_started.set()
            assert release_stage.wait(5)
            return value["items"]

        kwargs["select"] = select
        expected = [1]
    else:
        original_deepcopy = read_cache.deepcopy

        def blocked_deepcopy(value):
            if isinstance(value, dict) and value.get("marker") == "blocked":
                stage_started.set()
                assert release_stage.wait(5)
            return original_deepcopy(value)

        monkeypatch.setattr(read_cache, "deepcopy", blocked_deepcopy)

    def other():
        other_started.set()
        return "other"

    with ThreadPoolExecutor(max_workers=2) as pool:
        blocked = pool.submit(read_cache.cached, ("blocked",), lambda: pytest.fail("cache miss"), **kwargs)
        assert stage_started.wait(5)
        try:
            unrelated = pool.submit(read_cache.cached, ("copy-other",), other)
            assert other_started.wait(5)
            assert unrelated.result(timeout=5) == "other"
        finally:
            release_stage.set()
        assert blocked.result(timeout=5) == expected


def test_clear_does_not_allow_an_old_build_to_repopulate(monkeypatch):
    waiter_blocked = ThreadEvent()
    monkeypatch.setattr(read_cache, "Event", _observed_event(waiter_blocked))
    old_started = ThreadEvent()
    release_old = ThreadEvent()
    new_started = ThreadEvent()

    def old_build():
        old_started.set()
        assert release_old.wait(5)
        return "old"

    def new_build():
        new_started.set()
        return "new"

    with ThreadPoolExecutor(max_workers=3) as pool:
        old_leader = pool.submit(read_cache.cached, ("clear-race",), old_build)
        assert old_started.wait(5)
        old_waiter = pool.submit(read_cache.cached, ("clear-race",), old_build)
        assert waiter_blocked.wait(5)

        read_cache.clear()
        fresh = pool.submit(read_cache.cached, ("clear-race",), new_build)
        assert new_started.wait(5)
        assert fresh.result(timeout=5) == "new"
        release_old.set()
        assert old_leader.result(timeout=5) == "old"
        assert old_waiter.result(timeout=5) == "old"

    assert read_cache.cached(("clear-race",), lambda: pytest.fail("old build repopulated cache")) == "new"


def test_nested_keys_work_and_recursive_same_key_fails_without_hanging():
    calls = []

    def outer():
        calls.append("outer")
        return read_cache.cached(("inner",), lambda: calls.append("inner") or 1)

    assert read_cache.cached(("outer",), outer) == 1
    assert read_cache.cached(("outer",), outer) == 1
    assert calls == ["outer", "inner"]

    with pytest.raises(RuntimeError, match="recursive cache build"):
        read_cache.cached(
            ("recursive",),
            lambda: read_cache.cached(("recursive",), lambda: "unreachable"),
        )
    assert read_cache.cached(("recursive",), lambda: "retry") == "retry"
