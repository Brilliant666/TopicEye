"""Formal Runtime reuses the preview lifecycle, without preview-only settings."""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests_rardar_selection.test_local_preview_entry import ENTRY, HELPER, ROOT, literal, run_ps


def test_runtime_dispatch_does_not_enter_legacy_selection_startup() -> None:
    source = ENTRY.read_text(encoding="utf-8")
    dispatch = source[source.index("if ($Command -in @('start', 'stop', 'restart', 'status', 'build'))") :]
    assert 'Invoke-RardarPreview "preview-$Command" -RuntimeMode' in dispatch
    assert '"start" { Start-Rardar }' not in dispatch
    assert '"status" { Show-Status; Show-RardarSelectionStatus }' not in dispatch
    shared = HELPER.read_text(encoding="utf-8")
    assert "Start-Postgres" not in shared
    assert "Resolve-LocalSelectionSource" not in shared
    assert "Sync-RardarData" not in shared


@pytest.mark.parametrize("wrong_field", [None, "data", "ports"])
def test_runtime_config_uses_original_data_and_fixed_ports(tmp_path: Path, wrong_field: str | None) -> None:
    original = tmp_path / "original"
    alternate = tmp_path / "alternate"
    original.mkdir()
    alternate.mkdir()
    config = {
        "schemaVersion": 1,
        "repository": str(tmp_path),
        "backendPort": 8102,
        "frontendPort": 3000,
        "postgresPort": 55433,
        "dataDirectory": str(alternate if wrong_field == "data" else original),
        "budgetIdentityDataDirectory": str(original),
        "database": "original_db",
        "databaseUser": "existing_user",
    }
    if wrong_field == "ports":
        config["frontendPort"] = 54190
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = run_ps(
        tmp_path,
        f"""
$script:ManagedRuntimeMode=$true; $PgPort=55433; $MirrorRoot={literal(original)}
$script:PreviewConfigPath={literal(config_path)}
Get-PreviewConfig | ConvertTo-Json -Compress
""",
    )
    if wrong_field:
        assert result.returncode != 0
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["dataDirectory"] == str(original)


def test_formal_entry_rejects_development_repository_before_process_work(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
function Read-State { return [pscustomobject]@{repository='different-repository'} }
function Start-AppProcess { throw 'MUST_NOT_START' }
function Stop-PreviewState { throw 'MUST_NOT_STOP' }
Invoke-RardarPreview preview-start -RuntimeMode
""",
    )
    assert result.returncode != 0
    assert "existing recorded repository" in result.stderr
    assert "MUST_NOT_" not in result.stderr


def test_runtime_stop_preserves_identity_for_next_start(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    config = {
        "schemaVersion": 1,
        "repository": str(tmp_path),
        "backendPort": 8102,
        "frontendPort": 3000,
        "postgresPort": 55433,
        "dataDirectory": str(original),
        "budgetIdentityDataDirectory": str(original),
        "database": "original_db",
        "databaseUser": "original_role",
    }
    (runtime / "config.json").write_text(json.dumps(config), encoding="utf-8")
    state = {"repository": str(tmp_path), "backend": None, "frontend": None}
    (runtime / "runtime.json").write_text(json.dumps(state), encoding="utf-8")
    for relative in ["python.exe", "node.exe", "psql.exe", "node_modules/next/dist/bin/next"]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    result = run_ps(
        tmp_path,
        f"""
$env:LOCALAPPDATA=$RepoRoot; $RuntimeRoot={literal(runtime)}; $BackendRoot=$RepoRoot; $FrontendRoot=$RepoRoot
$MirrorRoot={literal(original)}; $PgPort=55433; $Psql=Join-Path $RepoRoot 'psql.exe'
$StatePath=Join-Path $RuntimeRoot 'runtime.json'; $script:PreviewStatePath=$StatePath
function Read-State {{ return Read-PreviewJson $StatePath }}
Stop-PreviewState (Read-State)
if (Test-Path -LiteralPath $StatePath) {{ throw 'PID_STATE_NOT_REMOVED' }}
function git {{ $global:LASTEXITCODE=0; if('status' -notin $args){{ return ('a'*40) }} }}
function Get-PreviewBuild {{ return [pscustomobject]@{{buildId='built-once'}} }}
function Assert-PreviewDatabase {{ }}
function Test-PreviewState {{ return $false }}
function Get-NetTCPConnection {{ return $null }}
function Start-AppProcess {{ throw 'START_ALLOWED_WITH_DURABLE_IDENTITY' }}
Invoke-RardarPreview preview-start -RuntimeMode
""",
    )
    assert result.returncode != 0
    assert "START_ALLOWED_WITH_DURABLE_IDENTITY" in result.stderr
    assert (runtime / "config.json").exists()
    assert not (runtime / "runtime.json").exists()


def test_new_preview_discovers_original_database_after_runtime_stop(tmp_path: Path) -> None:
    original = tmp_path / "original"
    preview = tmp_path / "preview-data"
    runtime = tmp_path / "runtime"
    for path in (original, preview, runtime):
        path.mkdir()
    (runtime / "config.json").write_text(
        json.dumps({"repository": "original-runtime", "database": "preserved_db", "databaseUser": "preserved_role"}),
        encoding="utf-8",
    )
    # Default preview data is obtained from TEMP; no real managed assets touched.
    (tmp_path / "rardar-refocus-preview-data").mkdir()
    result = run_ps(
        tmp_path,
        f"""
$env:TEMP=$RepoRoot; $RuntimeRoot={literal(runtime)}; $MirrorRoot={literal(original)}; $PgPort=55433
$script:ManagedRuntimeMode=$false; $script:PreviewConfigPath=Join-Path $RepoRoot 'new-preview-config.json'
function Read-State {{ return $null }}
Get-PreviewConfig | ConvertTo-Json -Compress
""",
    )
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout.strip())
    assert config["database"] == "preserved_db"
    assert config["databaseUser"] == "preserved_role"
    assert config["budgetIdentityDataDirectory"] == str(original)


def test_formal_start_keeps_scheduler_and_original_budget_without_migrations(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
$env:LOCALAPPDATA=$RepoRoot; $RuntimeRoot=Join-Path $RepoRoot 'runtime'; $BackendRoot=$RepoRoot; $FrontendRoot=$RepoRoot; $Psql=$PSHOME
function Read-State { return [pscustomobject]@{repository=$RepoRoot; database='original_db'} }
function Get-PreviewConfig { return [pscustomobject]@{repository=$RepoRoot;backendPort=8102;frontendPort=3000;postgresPort=55433;database='original_db';databaseUser='role';dataDirectory='original-data';budgetIdentityDataDirectory='original-data'} }
function git { $global:LASTEXITCODE=0; if('status' -notin $args){ return ('a'*40) } }
function Test-Path { return $true }
function Read-PreviewJson { return $null }
function Get-PreviewBuild { return [pscustomobject]@{buildId='built-once'} }
function Assert-PreviewDatabase { }
function Test-PreviewState { return $false }
function Get-NetTCPConnection { return $null }
function Start-AppProcess($executable,$arguments,$directory,$logs,$environment) {
    [pscustomobject]@{arguments=$arguments;environment=$environment} | ConvertTo-Json -Depth 4 -Compress | Write-Host
    throw 'CAPTURED_WITHOUT_STARTING'
}
function Stop-PreviewState { }
Invoke-RardarPreview preview-start -RuntimeMode
""",
    )
    assert result.returncode != 0
    assert "CAPTURED_WITHOUT_STARTING" in result.stderr
    captured = json.loads(result.stdout.strip())
    environment = captured["environment"]
    assert environment["SCHEDULER_ENABLED"] == "true"
    assert environment["RARDAR_DAILY_OPERATIONS_ENABLED"] == "true"
    assert environment["RARDAR_STARTUP_CATCHUP_ENABLED"] == "false"
    assert environment["RARDAR_BUDGET_IDENTITY_DATA_DIR"] == "original-data"
    assert environment["RARDAR_INTELLIGENCE_DATA_DIR"] == "original-data"
    assert environment["AUTO_CREATE_TABLES_ON_STARTUP"] == "false"
    assert environment["STARTUP_SEQUENCE_SYNC_ENABLED"] == "false"
    assert environment["STARTUP_SEED_ENABLED"] == "false"
    assert environment["ADMIN_SEED_ENABLED"] == "false"
    assert captured["arguments"][-2:] == ["--lifespan", "on"]


@pytest.mark.parametrize("enabled", [False, True])
def test_actual_lifespan_sequence_gate_preserves_default_and_skips_when_disabled(monkeypatch, enabled: bool) -> None:
    """Replay the actual lifespan statement, without starting DB/seeds/scheduler."""
    module = ast.parse((ROOT / "backend/app/main.py").read_text(encoding="utf-8"))
    lifespan = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan")
    gate = next(
        node
        for node in lifespan.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Attribute)
        and node.test.attr == "STARTUP_SEQUENCE_SYNC_ENABLED"
    )
    function = ast.AsyncFunctionDef(
        name="replay",
        args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[gate],
        decorator_list=[],
    )
    program = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    sync = AsyncMock()
    fake_module = ModuleType("app.core.sequence_health")
    fake_module.ensure_sequences_synced = sync
    monkeypatch.setitem(sys.modules, "app.core.sequence_health", fake_module)
    context = {"settings": SimpleNamespace(STARTUP_SEQUENCE_SYNC_ENABLED=enabled), "logger": Mock()}
    exec(compile(program, "<actual-lifespan-gate>", "exec"), context)
    asyncio.run(context["replay"]())
    assert sync.await_count == int(enabled)
    assert "STARTUP_SEQUENCE_SYNC_ENABLED: bool = True" in (ROOT / "backend/app/core/config.py").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("enabled,window_open", [(False, True), (True, True), (True, False)])
def test_startup_catchup_switch_keeps_lease_recovery_without_paid_run(
    monkeypatch, enabled: bool, window_open: bool
) -> None:
    module = ast.parse((ROOT / "backend/app/scheduler.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_rardar_startup_catchup"
    )
    program = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    upsert = AsyncMock()
    recover = AsyncMock()
    daily = AsyncMock()
    daily._job_name = "daily"
    daily._job_description = "daily-description"
    fake_module = ModuleType("app.services.job_tracker")
    fake_module._upsert_job_config = upsert
    fake_module.recover_rardar_daily_lease = recover
    monkeypatch.setitem(sys.modules, "app.services.job_tracker", fake_module)
    context = {
        "settings": SimpleNamespace(RARDAR_STARTUP_CATCHUP_ENABLED=enabled),
        "_rardar_daily_operations": daily,
        "_rardar_daily_window_open": lambda: window_open,
    }
    exec(compile(program, "<actual-startup-catchup>", "exec"), context)
    asyncio.run(context["_rardar_startup_catchup"]())
    upsert.assert_awaited_once_with("rardar_daily_operations", "daily", "daily-description")
    recover.assert_awaited_once()
    assert daily.await_count == int(enabled and window_open)
    source = (ROOT / "backend/app/scheduler.py").read_text(encoding="utf-8")
    # Catch-up and the two daily slots must enter the same guarded operation;
    # the retired hourly cadence is no longer the product contract.
    assert "trigger=_rardar_daily_trigger()," in source
    assert "return OrTrigger(" in source
    assert 'CronTrigger(hour="8-23", minute=30, timezone="Asia/Shanghai")' not in source
    assert "RARDAR_STARTUP_CATCHUP_ENABLED: bool = True" in (ROOT / "backend/app/core/config.py").read_text(
        encoding="utf-8"
    )
