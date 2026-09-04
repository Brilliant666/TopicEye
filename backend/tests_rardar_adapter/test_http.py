from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving import build_serving_projection, install_serving_projection, source_hashes
from tests_rardar_selection.build_e2e_fixture import _build as build_selection_fixture

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"
DISCOVER_FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_discover"
BACKEND = Path(__file__).parents[1]


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _server(data_dir: Path | None, *, rardar_mode: bool = True) -> Iterator[str]:
    port = _free_port()
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(BACKEND),
            "DATABASE_URL": "postgresql+asyncpg://adapter:adapter@127.0.0.1:5432/adapter",
            "RARDAR_PRODUCT_MODE": "true" if rardar_mode else "false",
            "RARDAR_INTELLIGENCE_DATA_DIR": str(data_dir) if data_dir is not None else "",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests_rardar_adapter.http_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    client = httpx.Client(trust_env=False)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"test HTTP server exited early: {output}")
            try:
                client.get(f"{url}/openapi.json", timeout=0.5).raise_for_status()
                break
            except (httpx.HTTPError, OSError):
                time.sleep(0.05)
        else:
            raise AssertionError("test HTTP server did not become ready")
        yield url
    finally:
        client.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _combined_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES / "revision-a", root)
    shutil.copytree(
        FIXTURES / "revision-b" / "generations" / "fixture-explosion-b",
        root / "generations" / "fixture-explosion-b",
    )
    for revision in ("fixture-explosion-a", "fixture-explosion-b"):
        shutil.copyfile(
            FIXTURES / ("revision-a" if revision.endswith("a") else "revision-b") / "current.json",
            root / "current.json",
        )
        board = RardarIntelligenceAdapter.from_config(str(root)).load_explosion_board()
        manifest_sha, explosion_sha = source_hashes(root, revision)
        built = build_serving_projection(
            board=board,
            source_manifest_sha256=manifest_sha,
            source_explosion_sha256=explosion_sha,
            synced_at=None,
            source_host=None,
            cache_root=root / "profile-cache",
        )
        install_serving_projection(root, built)
    shutil.copyfile(FIXTURES / "revision-a" / "current.json", root / "current.json")
    shutil.copyfile(root / "serving" / "sources" / "fixture-explosion-a.json", root / "serving" / "current.json")
    return root


def _selection_root(tmp_path: Path) -> Path:
    root = tmp_path / "selection-data"
    shutil.copytree(DISCOVER_FIXTURE, root)
    asyncio.run(build_selection_fixture(root))
    return root


def _content_inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_real_http_pointer_switch_and_fail_closed_recovery(tmp_path: Path) -> None:
    root = _combined_root(tmp_path)
    endpoint = "/api/v1/rardar/explosion-board"
    with _server(root) as url, httpx.Client(trust_env=False) as client:
        first = client.get(f"{url}{endpoint}", timeout=10)
        assert first.status_code == 200
        assert first.json()["generationId"] == "fixture-explosion-a"

        staged = root / "serving" / "current.next.json"
        shutil.copyfile(root / "serving" / "sources" / "fixture-explosion-b.json", staged)
        os.replace(staged, root / "serving" / "current.json")
        second = client.get(f"{url}{endpoint}", timeout=10)
        assert second.status_code == 200
        assert second.json()["generationId"] == "fixture-explosion-b"

        healthy_pointer = (root / "serving" / "current.json").read_bytes()
        (root / "serving" / "current.json").write_bytes(b"{broken\n")
        damaged = client.get(f"{url}{endpoint}", timeout=10)
        assert damaged.status_code == 503
        assert damaged.json()["detail"]["code"] == "rardar_serving_pointer_invalid"

        staged.write_bytes(healthy_pointer)
        os.replace(staged, root / "serving" / "current.json")
        recovered = client.get(f"{url}{endpoint}", timeout=10)
        assert recovered.status_code == 200
        assert recovered.json()["generationId"] == "fixture-explosion-b"


def test_real_http_default_topic_eye_mode_is_404(tmp_path: Path) -> None:
    root = _combined_root(tmp_path)
    with _server(root, rardar_mode=False) as url:
        response = httpx.get(f"{url}/api/v1/rardar/explosion-board", timeout=10, trust_env=False)
    assert response.status_code == 404


def test_real_http_serving_today_and_project_are_etag_cached(tmp_path: Path) -> None:
    root = _combined_root(tmp_path)
    with _server(root) as url, httpx.Client(trust_env=False) as client:
        today = client.get(f"{url}/api/v1/rardar/today", timeout=10)
        assert today.status_code == 200
        assert today.headers["cache-control"] == "private, max-age=15, stale-while-revalidate=45"
        etag = today.headers["etag"]
        cached = client.get(f"{url}/api/v1/rardar/today", headers={"If-None-Match": etag}, timeout=10)
        assert cached.status_code == 304

        payload = today.json()
        project = payload["exactRanked"][0]
        detail = client.get(
            f"{url}/api/v1/rardar/projects/{project['githubRepositoryId']}",
            params={"generationId": payload["generationId"]},
            timeout=10,
        )
        assert detail.status_code == 200
        assert detail.json()["profile"]["githubRepositoryId"] == project["githubRepositoryId"]
        assert detail.headers["etag"]


def test_real_http_rardar_mode_reports_unconfigured_data() -> None:
    with _server(None) as url:
        response = httpx.get(f"{url}/api/v1/rardar/explosion-board", timeout=10, trust_env=False)
    assert response.status_code == 200
    assert response.json()["state"] == "not_synced"
    assert response.json()["reason"] == "real_data_not_synced"
    assert response.json()["dataMode"] == "real"


def test_real_http_selection_is_static_etag_cached_and_fails_closed(tmp_path: Path) -> None:
    root = _selection_root(tmp_path)
    before = _content_inventory(root)
    with _server(root) as url, httpx.Client(trust_env=False) as client:
        response = client.get(f"{url}/api/v1/rardar/discover/selection", timeout=10)
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "shadow"
        assert payload["status"] in {"ready", "stale"}
        assert payload["generation"]
        assert payload["sourceTodayGeneration"]
        assert payload["items"]
        etag = response.headers["etag"]
        cached = client.get(
            f"{url}/api/v1/rardar/discover/selection",
            headers={"If-None-Match": etag},
            timeout=10,
        )
        assert cached.status_code == 304

        project = payload["items"][0]
        detail = client.get(
            f"{url}/api/v1/rardar/discover/selection/projects/{project['githubRepositoryId']}",
            params={"selectionGeneration": payload["generation"]},
            timeout=10,
        )
        assert detail.status_code == 200
        assert detail.headers["etag"] == etag
        assert detail.json()["context"]["card"] == project

        generation = root / "discover-worth-seeing" / "generations" / payload["generation"]
        serving_path = generation / "serving" / "selection.json"
        healthy = serving_path.read_bytes()
        serving_path.write_bytes(b"{}\n")
        damaged = client.get(f"{url}/api/v1/rardar/discover/selection", timeout=10)
        assert damaged.status_code == 503
        assert damaged.json()["status"] == "invalid"
        assert damaged.json()["items"] == []
        serving_path.write_bytes(healthy)
        recovered = client.get(f"{url}/api/v1/rardar/discover/selection", timeout=10)
        assert recovered.status_code == 200
        assert recovered.json()["generation"] == payload["generation"]
    assert _content_inventory(root) == before
