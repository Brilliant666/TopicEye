"""Root-installed host gate for one private Rardar material recovery grant.

Install a reviewed copy under /usr/local/sbin, owned by root. A grant is a
root-owned regular JSON file below the fixed private directory, not a path or
command supplied by the application user. Do not execute this file from a
deployment-user-writable checkout as root.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path


GRANT_DIR = Path("/etc/rardar-product/recovery-authorizations")
CONTAINER = "rardar-product-backend"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,119}\Z")


def _root_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError("recovery_grant_directory_unsafe")


def _read_grant(identifier: str) -> dict:
    if not IDENTIFIER.fullmatch(identifier):
        raise ValueError("recovery_grant_identifier_invalid")
    for path in (Path("/etc"), Path("/etc/rardar-product"), GRANT_DIR):
        _root_directory(path)
    path = GRANT_DIR / f"{identifier}.json"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o077
            or info.st_size > 4096
        ):
            raise ValueError("recovery_grant_file_unsafe")
        raw = os.read(descriptor, 4097)
    finally:
        os.close(descriptor)
    if len(raw) > 4096:
        raise ValueError("recovery_grant_file_oversized")
    grant = json.loads(raw)
    if not isinstance(grant, dict) or grant.get("authorizationId") != identifier:
        raise ValueError("recovery_grant_identity_mismatch")
    return grant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization-id", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("this host gate must run as root")
    grant = _read_grant(args.authorization_id)
    name = grant.get("repository")
    mode = grant.get("mode")
    plan = grant.get("approvedPlanDigest")
    if (
        not isinstance(name, str)
        or mode not in {"cache-only", "generate"}
        or not isinstance(plan, str)
    ):
        raise ValueError("recovery_grant_scope_invalid")
    inspection = subprocess.run(
        ["/usr/bin/docker", "inspect", "--format", "{{.State.Running}}", CONTAINER],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if inspection.stdout.strip() != "true":
        raise ValueError("recovery_backend_not_running")
    completed = subprocess.run(
        [
            "/usr/bin/docker",
            "exec",
            "-i",
            CONTAINER,
            "python",
            "-m",
            "scripts.correct_rardar_material_once",
            "--repository",
            name,
            "--mode",
            mode,
            "--apply",
            "--plan-digest",
            plan,
            "--authorization-stdin",
        ],
        input=json.dumps(grant, separators=(",", ":"), sort_keys=True),
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if completed.returncode:
        # Never print arbitrary stderr: it may include upstream exception text.
        raise RuntimeError(f"recovery_apply_failed_exit_{completed.returncode}")
    try:
        result = json.loads(completed.stdout.strip())
    except ValueError as exc:
        raise ValueError("recovery_apply_result_invalid") from exc
    if not isinstance(result, dict):
        raise ValueError("recovery_apply_result_invalid")
    allowed = {
        "status",
        "repository",
        "projectId",
        "providerRequests",
        "sourceRequests",
        "errorCode",
        "outerErrorCode",
        "stage",
        "diagnostic",
        "materialState",
        "qualityState",
        "profileRevision",
        "receipt",
        "originalStatus",
        "reason",
    }
    print(
        json.dumps(
            {key: value for key, value in result.items() if key in allowed},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
