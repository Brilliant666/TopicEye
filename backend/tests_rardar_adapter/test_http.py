from __future__ import annotations

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

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"
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
    return root


def test_real_http_pointer_switch_and_fail_closed_recovery(tmp_path: Path) -> None:
    root = _combined_root(tmp_path)
    endpoint = "/api/v1/rardar/explosion-board"
    with _server(root) as url, httpx.Client(trust_env=False) as client:
        first = client.get(f"{url}{endpoint}", timeout=10)
        assert first.status_code == 200
        assert first.json()["generationId"] == "fixture-explosion-a"

        staged = root / "current.next.json"
        shutil.copyfile(FIXTURES / "revision-b" / "current.json", staged)
        os.replace(staged, root / "current.json")
        second = client.get(f"{url}{endpoint}", timeout=10)
        assert second.status_code == 200
        assert second.json()["generationId"] == "fixture-explosion-b"

        healthy_pointer = (root / "current.json").read_bytes()
        (root / "current.json").write_bytes(b"{broken\n")
        damaged = client.get(f"{url}{endpoint}", timeout=10)
        assert damaged.status_code == 503
        assert damaged.json()["detail"]["code"] == "rardar_current_pointer_invalid"

        staged.write_bytes(healthy_pointer)
        os.replace(staged, root / "current.json")
        recovered = client.get(f"{url}{endpoint}", timeout=10)
        assert recovered.status_code == 200
        assert recovered.json()["generationId"] == "fixture-explosion-b"


def test_real_http_default_topic_eye_mode_is_404(tmp_path: Path) -> None:
    root = _combined_root(tmp_path)
    with _server(root, rardar_mode=False) as url:
        response = httpx.get(f"{url}/api/v1/rardar/explosion-board", timeout=10, trust_env=False)
    assert response.status_code == 404


def test_real_http_rardar_mode_reports_unconfigured_data() -> None:
    with _server(None) as url:
        response = httpx.get(f"{url}/api/v1/rardar/explosion-board", timeout=10, trust_env=False)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rardar_intelligence_not_configured"
