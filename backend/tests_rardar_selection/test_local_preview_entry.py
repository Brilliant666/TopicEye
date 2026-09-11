"""Exercise the real preview shell functions with process/HTTP doubles only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/rardar-preview.ps1"
ENTRY = ROOT / "scripts/rardar-local.ps1"


def literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell 7 unavailable")
    harness = tmp_path / "preview-test.ps1"
    harness.write_text(
        "$ErrorActionPreference='Stop'\n"
        f". {literal(HELPER)}\n"
        f"$RepoRoot={literal(tmp_path)}\n"
        # These are process doubles, but Join-Path still resolves their drive.
        # Use the test filesystem so the same identity checks run on Linux CI.
        f"$Python={literal(tmp_path / 'python.exe')}; $Node={literal(tmp_path / 'node.exe')}\n"
        f"$PgRoot={literal(tmp_path / 'pgsql')}; $PgCtl={literal(tmp_path / 'pgsql/bin/pg_ctl.exe')}\n" + body,
        encoding="utf-8",
    )
    return subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-File", str(harness)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def test_preview_wiring_has_no_automatic_build_migration_or_scheduler() -> None:
    source = HELPER.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    assert "Invoke-RardarPreview $Command" in entry
    assert "function Start-AppProcess" in entry
    assert source.count("Start-AppProcess ") == 2
    assert "$lifespan = if ($RuntimeMode) { 'on' } else { 'off' }" in source
    assert "'--lifespan', $lifespan" in source
    assert "SCHEDULER_ENABLED = if ($RuntimeMode) { 'true' } else { 'false' }" in source
    assert "RARDAR_DAILY_OPERATIONS_ENABLED = 'true'" in source
    assert "RARDAR_BUDGET_IDENTITY_DATA_DIR = $config.budgetIdentityDataDirectory" in source
    assert "Start-Postgres" not in source
    assert "npm ci" not in source
    assert "alembic" not in source
    assert "Stop-Process -Name" not in source
    assert source.index("Assert-PreviewDatabase $config") < source.index("if ($state) { Stop-PreviewState $state }")
    assert "RARDAR_ISOLATED_PREVIEW = if ($RuntimeMode) { 'false' } else { 'true' }" in source
    assert "$buildDirectory = if ($RuntimeMode) { '.next' } else { '.next-preview' }" in source
    assert "$buildDirectory = if ($script:ManagedRuntimeMode) { '.next' } else { '.next-preview' }" in source


@pytest.mark.parametrize("change", ["port", "identity", "same_data", "secret"])
def test_managed_config_rejects_unsafe_binding(tmp_path: Path, change: str) -> None:
    original = tmp_path / "original"
    preview = tmp_path / "preview"
    original.mkdir()
    preview.mkdir()
    config = {
        "schemaVersion": 1,
        "repository": str(tmp_path),
        "backendPort": 54181,
        "frontendPort": 54180,
        "postgresPort": 55433,
        "dataDirectory": str(preview),
        "budgetIdentityDataDirectory": str(original),
        "database": "existing",
        "databaseUser": "existing_role",
    }
    if change == "port":
        config["frontendPort"] = 3000
    elif change == "identity":
        config["budgetIdentityDataDirectory"] = str(preview)
    elif change == "same_data":
        config["dataDirectory"] = str(original)
    else:
        config["apiKey"] = "not-a-real-key"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = run_ps(
        tmp_path,
        f"""
$PgPort=55433; $MirrorRoot={literal(original)}
$script:PreviewConfigPath={literal(path)}
Get-PreviewConfig | Out-Null
""",
    )
    assert result.returncode != 0
    assert "not-a-real-key" not in result.stderr


@pytest.mark.parametrize("port", [54190, 54190.5, "54190"])
def test_managed_config_json_roundtrip_accepts_only_integer_ports(tmp_path: Path, port: object) -> None:
    original = tmp_path / "original"
    preview = tmp_path / "preview"
    original.mkdir()
    preview.mkdir()
    path = tmp_path / "config.json"
    config = {
        "schemaVersion": 1,
        "repository": str(tmp_path),
        "backendPort": 54191,
        "frontendPort": port,
        "postgresPort": 55433,
        "dataDirectory": str(preview),
        "budgetIdentityDataDirectory": str(original),
        "database": "existing",
        "databaseUser": "existing_role",
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    result = run_ps(
        tmp_path,
        f"""
$PgPort=55433; $MirrorRoot={literal(original)}
$script:PreviewConfigPath={literal(path)}
$config=Get-PreviewConfig
Write-PreviewJson $script:PreviewConfigPath $config
Get-PreviewConfig | ConvertTo-Json -Compress
""",
    )
    if type(port) is int:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout.strip())["frontendPort"] == port
    else:
        assert result.returncode != 0


def test_stop_checks_all_processes_before_first_termination(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
$state=[pscustomobject]@{repository=$RepoRoot;frontend=[pscustomobject]@{pid=10;port=54180;listener=$true};backend=[pscustomobject]@{pid=11;port=54181;listener=$true}}
function Assert-PreviewProcess($record,$required) { if($record.pid -eq 11){throw 'PID_REUSED'}; return $true }
function taskkill.exe { throw 'TERMINATION_MUST_NOT_OCCUR' }
Stop-PreviewState $state
""",
    )
    assert result.returncode != 0
    assert "PID_REUSED" in result.stderr
    assert "TERMINATION_MUST_NOT_OCCUR" not in result.stderr


@pytest.mark.parametrize("mutation", ["createdAtTicks", "executable", "commandHash"])
def test_pid_reuse_and_process_identity_fail_closed(tmp_path: Path, mutation: str) -> None:
    result = run_ps(
        tmp_path,
        f"""
$command="$RepoRoot backend uvicorn --port 54181"
$script:fake=[pscustomobject]@{{ExecutablePath=$Python;CommandLine=$command;CreationDate=[datetime]'2026-09-11T01:00:00Z'}}
function Get-CimInstance {{ return $script:fake }}
$record=[pscustomobject]@{{pid=123;port=54181;executable=$Python;createdAtTicks=$script:fake.CreationDate.ToUniversalTime().Ticks.ToString();commandHash=(Get-PreviewHash $command);listener=$null}}
$record.{mutation}='changed'
Assert-PreviewProcess $record $false
""",
    )
    assert result.returncode != 0
    assert "identity changed" in result.stderr


def test_dead_root_with_unowned_listener_is_not_stopped(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
function Get-CimInstance { return $null }
function Get-NetTCPConnection { return [pscustomobject]@{OwningProcess=999} }
$record=[pscustomobject]@{pid=123;port=54181;listener=$null}
Assert-PreviewProcess $record $false
""",
    )
    assert result.returncode != 0
    assert "Unowned process" in result.stderr


def test_process_identity_survives_state_json_roundtrip(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
$script:fake=[pscustomobject]@{ExecutablePath=$Python;CommandLine="$RepoRoot backend uvicorn --port 54181";CreationDate=[datetime]'2026-09-11T01:00:00Z'}
function Get-CimInstance { return $script:fake }
$record=Get-PreviewProcessRecord 123 54181
$path=Join-Path $RepoRoot 'process.json'
Write-PreviewJson $path $record
$restored=Read-PreviewJson $path
Assert-PreviewProcess $restored $false
""",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_healthy_start_returns_without_launch(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
$env:LOCALAPPDATA=$RepoRoot; $BackendRoot=$RepoRoot; $FrontendRoot=$RepoRoot; $Psql=$PSHOME
function Read-PreviewJson { return [pscustomobject]@{status='healthy'} }
function Get-PreviewConfig { return [pscustomobject]@{backendPort=54181;frontendPort=54180} }
function git { $global:LASTEXITCODE=0; if('status' -notin $args){ return ('a'*40) } }
function Test-Path { return $true }
function Get-PreviewBuild { return [pscustomobject]@{buildId='same'} }
function Assert-PreviewDatabase { }
function Test-PreviewState { return $true }
function Start-AppProcess { throw 'MUST_NOT_LAUNCH' }
function Stop-PreviewState { throw 'MUST_NOT_STOP' }
Invoke-RardarPreview preview-start
""",
    )
    assert result.returncode == 0, result.stderr
    assert "already healthy" in result.stdout


@pytest.mark.parametrize("dirty", [False, True])
def test_status_reports_source_tree_cleanliness(tmp_path: Path, dirty: bool) -> None:
    changed_file = " M backend/app/main.py" if dirty else ""
    result = run_ps(
        tmp_path,
        f"""
$env:LOCALAPPDATA=$RepoRoot; $BackendRoot=$RepoRoot; $FrontendRoot=$RepoRoot; $Psql=$PSHOME
function Read-PreviewJson {{ return [pscustomobject]@{{status='healthy'}} }}
function Get-PreviewConfig {{ return [pscustomobject]@{{backendPort=54181;frontendPort=54180}} }}
function git {{ $global:LASTEXITCODE=0; if('status' -in $args){{ return '{changed_file}' }}; return ('a'*40) }}
function Test-Path {{ return $true }}
function Get-PreviewBuild {{ return [pscustomobject]@{{buildId='same'}} }}
function Assert-PreviewDatabase {{ }}
function Test-PreviewState {{ return $true }}
function Start-AppProcess {{ throw 'MUST_NOT_LAUNCH' }}
function Stop-PreviewState {{ throw 'MUST_NOT_STOP' }}
function Format-List {{ process {{ $_ | ConvertTo-Json -Compress }} }}
Invoke-RardarPreview preview-status
""",
    )
    status = json.loads(result.stdout.strip())
    assert status["worktreeClean"] is not dirty
    assert status["healthy"] is not dirty
    assert (result.returncode != 0) is dirty
    assert "MUST_NOT_" not in result.stderr


def test_build_failure_prevents_restart_stop(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        """
$env:LOCALAPPDATA=$RepoRoot; $BackendRoot=$RepoRoot; $FrontendRoot=$RepoRoot; $Psql=$PSHOME
function Read-PreviewJson { return [pscustomobject]@{status='healthy'} }
function Get-PreviewConfig { return [pscustomobject]@{backendPort=54181;frontendPort=54180} }
function git { $global:LASTEXITCODE=0; return ('a'*40) }
function Test-Path { return $true }
function Get-PreviewBuild { throw 'BUILD_MISMATCH' }
function Stop-PreviewState { throw 'MUST_NOT_STOP' }
Invoke-RardarPreview preview-restart
""",
    )
    assert result.returncode != 0
    assert "BUILD_MISMATCH" in result.stderr
    assert "MUST_NOT_STOP" not in result.stderr


@pytest.mark.parametrize("setting,expected", [("true", ".next-preview"), ("false", ".next")])
def test_preview_build_directory_does_not_replace_runtime(setting: str, expected: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    environment = dict(os.environ, RARDAR_ISOLATED_PREVIEW=setting)
    result = subprocess.run(
        [node, "-e", "console.log(require('./next.config.js').distDir)"],
        cwd=ROOT / "frontend",
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
    config = json.loads((ROOT / "frontend/tsconfig.json").read_text(encoding="utf-8"))
    assert ".next-preview/types/**/*.ts" in config["include"]
    assert ".next-preview/dev/types/**/*.ts" in config["include"]
