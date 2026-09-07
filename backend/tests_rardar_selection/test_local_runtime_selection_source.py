from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPOSITORY = Path(__file__).resolve().parents[2]
_RUNTIME_SCRIPT = _REPOSITORY / "scripts" / "rardar-local.ps1"


def _pwsh() -> str:
    executable = shutil.which("pwsh") or (shutil.which("powershell") if os.name == "nt" else None)
    if executable is None:
        pytest.skip("PowerShell is unavailable")
    return executable


def _resolver_source() -> str:
    source = _RUNTIME_SCRIPT.read_text(encoding="utf-8")
    start = source.index("function Resolve-LocalSelectionSource(")
    end = source.index("\nfunction Assert-RecordedRuntime(", start)
    return source[start:end]


def _ps_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_resolver(
    tmp_path: Path,
    *,
    validator_body: str = "$generation",
) -> subprocess.CompletedProcess[str]:
    harness = tmp_path / "resolve-selection-source.ps1"
    harness.write_text(
        "\n".join(
            (
                '$ErrorActionPreference = "Stop"',
                _resolver_source(),
                f"$dataRoot = {_ps_literal(tmp_path / 'mirror')}",
                f"$applicationRoot = {_ps_literal(_REPOSITORY / 'backend')}",
                "$validator = {",
                "    param($root, $generation)",
                f"    {validator_body}",
                "}",
                "$result = Resolve-LocalSelectionSource -DataRoot $dataRoot "
                "-PythonExecutable $PSHOME -ApplicationRoot $applicationRoot -NormalValidator $validator",
                "$result | ConvertTo-Json -Compress",
            )
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [_pwsh(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(harness)],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _pointer(*, state: str | None = None, policy: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "selectionGenerationId": "selection-test-generation",
        "sourceObservationSetId": "observation-test",
        "manifestSha256": "a" * 64,
        "activatedAt": "2026-09-07T08:00:00+00:00",
    }
    if state is not None:
        payload["activationState"] = state
    if policy is not None:
        payload["activationPolicyVersion"] = policy
    return payload


def _write_pointer(tmp_path: Path, payload: object) -> Path:
    pointer = tmp_path / "mirror" / "discover-worth-seeing" / "current.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return pointer


def _result(process: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout.strip().splitlines()[-1])


def test_missing_or_legacy_pointer_keeps_historical_shadow(tmp_path: Path) -> None:
    missing = _result(_run_resolver(tmp_path, validator_body='throw "validator must not run"'))
    assert missing == {
        "source": "shadow",
        "localShadowReview": True,
        "selectionGenerationId": None,
    }

    _write_pointer(tmp_path, _pointer())
    legacy = _result(_run_resolver(tmp_path, validator_body='throw "validator must not run"'))
    assert legacy == missing


@pytest.mark.parametrize("state", ["ready", "empty"])
def test_audited_healthy_pointer_selects_normal_serving(tmp_path: Path, state: str) -> None:
    _write_pointer(tmp_path, _pointer(state=state, policy="worth-seeing-activation-v2"))

    result = _result(_run_resolver(tmp_path))

    assert result == {
        "source": "normal",
        "localShadowReview": False,
        "selectionGenerationId": "selection-test-generation",
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-json", "invalid JSON"),
        ({"schemaVersion": 1}, "untrusted structure"),
        (_pointer(state="ready"), "activation metadata is incomplete"),
        (
            _pointer(state="degraded", policy="worth-seeing-activation-v2"),
            "not eligible for normal serving",
        ),
        (
            {**_pointer(state="ready", policy="worth-seeing-activation-v2"), "unexpected": True},
            "untrusted structure",
        ),
    ],
)
def test_damaged_or_untrusted_pointer_fails_closed(tmp_path: Path, payload: object, message: str) -> None:
    pointer = tmp_path / "mirror" / "discover-worth-seeing" / "current.json"
    pointer.parent.mkdir(parents=True)
    if isinstance(payload, str):
        pointer.write_text(payload, encoding="utf-8")
    else:
        pointer.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    process = _run_resolver(tmp_path)

    assert process.returncode != 0
    assert message in process.stderr


def test_audited_validator_must_confirm_the_same_generation(tmp_path: Path) -> None:
    _write_pointer(tmp_path, _pointer(state="ready", policy="worth-seeing-activation-v2"))

    process = _run_resolver(tmp_path, validator_body='"selection-other-generation"')

    assert process.returncode != 0
    assert "validation returned a mismatched generation" in process.stderr


def test_directory_cannot_replace_the_current_pointer(tmp_path: Path) -> None:
    pointer = tmp_path / "mirror" / "discover-worth-seeing" / "current.json"
    pointer.mkdir(parents=True)

    process = _run_resolver(tmp_path)

    assert process.returncode != 0
    assert "not a regular file" in process.stderr


def test_reparse_pointer_is_never_read_as_trusted_current(tmp_path: Path) -> None:
    target = tmp_path / "actual-current.json"
    target.write_text(
        json.dumps(_pointer(state="ready", policy="worth-seeing-activation-v2")),
        encoding="utf-8",
    )
    pointer = tmp_path / "mirror" / "discover-worth-seeing" / "current.json"
    pointer.parent.mkdir(parents=True)
    try:
        pointer.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    process = _run_resolver(tmp_path)

    assert process.returncode != 0
    assert "unsafe" in process.stderr


def test_runtime_wiring_uses_audited_loader_and_preserves_production_mode() -> None:
    source = _RUNTIME_SCRIPT.read_text(encoding="utf-8")

    assert "SelectionServingLoader(sys.argv[1]).load_with_etag()" in source
    assert 'RARDAR_LOCAL_SHADOW_REVIEW = if ($localShadowReview) { "true" } else { "false" }' in source
    assert "selectionSource = $selectionSource" in source
    assert '$frontendEnvironment = @{\n            NODE_ENV = "production"' in source
    assert "& $Node $next build --webpack" in source
    assert '@($next, "start", "--hostname", "127.0.0.1", "--port", "3000")' in source
