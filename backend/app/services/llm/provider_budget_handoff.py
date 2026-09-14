"""Offline, operator-authorized daily-ledger relocation; never a model client.

Account and stopped-source references are attestations, not cross-host locks.
No multi-writer reconciliation is attempted: divergent journals fail closed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from app.services.llm.provider_budget import (
    DAILY_TASK_ID,
    ProviderBudgetError,
    ProviderBudgetLedger,
    canonical,
    digest,
    plain,
)

FILES = ("provider-budget.json", "provider-budget-events.jsonl", "provider-budget-registration.json")
RECEIPT = "provider-budget-handoff.json"
MAX_BUNDLE_BYTES = 64_000_000
DAY_FILES = set(FILES) | {"provider-budget.lock", "provider-budget-registration.lock", "provider-execution.lock"}


def fail(code="provider_handoff_invalid"):
    raise ProviderBudgetError(code)


def reference(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,150}", value):
        fail("provider_handoff_reference_invalid")
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                fail("provider_handoff_duplicate_key")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=unique)


def source_path(value):
    if not isinstance(value, str):
        fail()
    path = (PureWindowsPath if "\\" in value or PureWindowsPath(value).drive else PurePosixPath)(value)
    if not path.is_absolute() or ".." in path.parts:
        fail("provider_handoff_source_path_invalid")
    return path


def read(path):
    plain(path)
    if not path.is_file() or path.stat().st_size > 2_000_000:
        fail()
    return path.read_bytes()


def inventory(root):
    plain(root)
    result = {}
    for entry in sorted(root.iterdir()):
        plain(entry)
        if entry.name in {"initialize.lock", "provider-execution.lock", RECEIPT}:
            if not entry.is_file():
                fail("provider_handoff_inventory_unknown")
            continue
        if entry.name == "interactive-waiters":
            if not entry.is_dir():
                fail("provider_handoff_inventory_unknown")
            for waiter in entry.iterdir():
                plain(waiter)
                if not waiter.is_file() or not re.fullmatch(r"[0-9a-f]{32}\.json", waiter.name):
                    fail("provider_handoff_inventory_unknown")
            continue
        try:
            if date.fromisoformat(entry.name).isoformat() != entry.name or not entry.is_dir():
                fail()
        except ValueError:
            fail("provider_handoff_inventory_unknown")
        for item in entry.iterdir():
            plain(item)
            if item.name not in DAY_FILES or not item.is_file():
                fail("provider_handoff_inventory_unknown")
        result[entry.name] = {name: read(entry / name) for name in FILES}
    if not result:
        fail("provider_handoff_empty")
    return result


def validate_day(day, raw, source_root):
    try:
        registered = strict_json(raw[FILES[2]])
        expected_path = str(source_path(source_root) / day / FILES[0])
        limit = registered["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            fail("provider_handoff_limit_invalid")
        if registered != {"taskId": DAILY_TASK_ID, "runId": f"daily-{day}", "path": expected_path, "limit": limit}:
            fail("provider_handoff_identity_mismatch")
        ledger = ProviderBudgetLedger(Path("unused"), f"daily-{day}", task_id=DAILY_TASK_ID, limit=limit)
        for line in raw[FILES[1]].splitlines():
            strict_json(line)
        summary, events = ledger._replay_bytes(raw[FILES[1]])
        saved = strict_json(raw[FILES[0]])
        if saved["digest"] != digest({k: v for k, v in saved.items() if k != "digest"}):
            fail()
        if saved["journalDigest"] not in {event["digest"] for event in events}:
            fail()
        # The saved snapshot must be an actual replay prefix, not merely signed JSON.
        prefix = next(i for i, event in enumerate(events) if event["digest"] == saved["journalDigest"])
        prefix_raw = b"\n".join(raw[FILES[1]].splitlines()[: prefix + 1]) + b"\n"
        if saved != ledger._replay_bytes(prefix_raw)[0]:
            fail()
        return summary
    except (KeyError, TypeError, ValueError):
        fail()


def export_bundle(root: Path, *, source_root: str, account_ref: str):
    """Read twice without creating source locks; source need not be stopped for dry-run."""
    reference(account_ref)
    first = inventory(root)
    second = inventory(root)
    if first != second:
        fail("provider_handoff_source_changed")
    days = {}
    for day, raw in first.items():
        summary = validate_day(day, raw, source_root)
        days[day] = {
            "summary": summary,
            "files": {
                name: {"sha256": sha(value), "base64": base64.b64encode(value).decode("ascii")}
                for name, value in raw.items()
            },
        }
    body = {"schemaVersion": 1, "sourceRoot": source_root, "accountRef": account_ref, "days": days}
    bundle = {**body, "digest": digest(body)}
    if len(canonical(bundle)) > MAX_BUNDLE_BYTES:
        fail("provider_handoff_bundle_too_large")
    return bundle


def verify_bundle(bundle, expected_digest, account_ref):
    reference(account_ref)
    if not isinstance(bundle, dict) or set(bundle) != {"schemaVersion", "sourceRoot", "accountRef", "days", "digest"}:
        fail()
    if len(canonical(bundle)) > MAX_BUNDLE_BYTES:
        fail("provider_handoff_bundle_too_large")
    source_path(bundle["sourceRoot"])
    if (
        bundle.get("digest") != expected_digest
        or digest({k: v for k, v in bundle.items() if k != "digest"}) != expected_digest
    ):
        fail("provider_handoff_digest_mismatch")
    if bundle.get("schemaVersion") != 1 or bundle.get("accountRef") != account_ref:
        fail("provider_handoff_account_mismatch")
    if not bundle.get("days"):
        fail()
    decoded = {}
    for day, item in bundle["days"].items():
        if set(item) != {"summary", "files"}:
            fail()
        if date.fromisoformat(day).isoformat() != day or set(item["files"]) != set(FILES):
            fail()
        raw = {}
        for name, record in item["files"].items():
            if set(record) != {"sha256", "base64"}:
                fail()
            value = base64.b64decode(record["base64"], validate=True)
            if len(value) > 2_000_000:
                fail()
            if sha(value) != record["sha256"]:
                fail("provider_handoff_digest_mismatch")
            raw[name] = value
        if validate_day(day, raw, bundle["sourceRoot"]) != item["summary"]:
            fail()
        decoded[day] = raw
    return decoded


def sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def publish_root(staging, target):
    """Atomic directory publish that never replaces even an empty competing root."""
    plain(staging)
    plain(target, missing=True)
    if os.name == "nt":
        # Windows rename rejects an existing destination, including an empty directory.
        os.rename(staging, target)
    elif sys.platform.startswith("linux"):
        import ctypes

        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, "renameat2", None)
        if rename is None:
            fail("provider_handoff_atomic_publish_unavailable")
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        # AT_FDCWD = -100; RENAME_NOREPLACE = 1. No unsafe rename fallback.
        if rename(-100, os.fsencode(staging), -100, os.fsencode(target), 1) != 0:
            fail("provider_handoff_atomic_publish_rejected")
    else:
        fail("provider_handoff_atomic_publish_unavailable")
    sync_directory(target.parent)


def import_bundle(
    bundle,
    target: Path,
    *,
    expected_digest: str,
    account_ref: str,
    stopped_source_ref: str | None = None,
    dry_run: bool = True,
):
    """Install into an absent root only; repeated import never rewrites newer usage.

    Runtime must be disabled and target parent under operator-exclusive control.
    Partial imports remain in a private sibling staging directory, never at target.
    """
    raw_days = verify_bundle(bundle, expected_digest, account_ref)
    plain(target, missing=True)
    receipt = {
        "schemaVersion": 1,
        "bundleDigest": expected_digest,
        "sourceRoot": bundle["sourceRoot"],
        "targetRoot": str(target),
        "accountRef": account_ref,
        "days": sorted(raw_days),
    }
    if target.exists():
        saved = strict_json(read(target / RECEIPT))
        if {k: v for k, v in saved.items() if k != "stoppedSourceRef"} != receipt:
            fail("provider_handoff_target_conflict")
        reference(saved.get("stoppedSourceRef"))
        current = inventory(target)
        if not set(raw_days).issubset(current):
            fail("provider_handoff_target_conflict")
        for day, raw in current.items():
            validate_day(day, raw, str(target))
            if day in raw_days and not raw[FILES[1]].startswith(raw_days[day][FILES[1]]):
                fail("provider_handoff_divergent_chain")
        return {"status": "already_imported", "days": len(raw_days), "writes": 0}
    if not dry_run:
        reference(stopped_source_ref)
        plain(target.parent)
        staging = target.with_name(f".{target.name}.handoff-{uuid4().hex}")
        plain(staging, missing=True)
        staging.mkdir(mode=0o700)
        for day, raw in raw_days.items():
            directory = staging / day
            directory.mkdir(mode=0o700)
            registration = strict_json(raw[FILES[2]])
            registration["path"] = str(target / day / FILES[0])
            values = {**raw, FILES[2]: canonical(registration)}
            for name, value in values.items():
                with (directory / name).open("xb") as handle:
                    handle.write(value)
                    handle.flush()
                    os.fsync(handle.fileno())
            sync_directory(directory)
        # Receipt is the last activation gate; it never claims cross-host fencing.
        receipt_value = {**receipt, "stoppedSourceRef": stopped_source_ref}
        with (staging / RECEIPT).open("xb") as handle:
            handle.write(canonical(receipt_value))
            handle.flush()
            os.fsync(handle.fileno())
        staged = inventory(staging)
        if set(staged) != set(raw_days) or strict_json(read(staging / RECEIPT)) != receipt_value:
            fail("provider_handoff_staging_invalid")
        for day, raw in staged.items():
            if validate_day(day, raw, str(target)) != bundle["days"][day]["summary"]:
                fail("provider_handoff_staging_invalid")
            if raw[FILES[0]] != raw_days[day][FILES[0]] or raw[FILES[1]] != raw_days[day][FILES[1]]:
                fail("provider_handoff_staging_invalid")
        sync_directory(staging)
        publish_root(staging, target)
    return {
        "status": "dry_run" if dry_run else "imported",
        "days": len(raw_days),
        "reserved": {d: bundle["days"][d]["summary"]["reserved"] for d in raw_days},
        "bundleDigest": expected_digest,
        "accountVerification": "not_verified_by_tool",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "import"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--digest")
    parser.add_argument("--stopped-source-ref")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.operation == "export":
            if not args.source_root or args.apply:
                fail()
            if args.bundle.absolute().is_relative_to(args.root.absolute()):
                fail("provider_handoff_output_inside_source")
            bundle = export_bundle(args.root, source_root=args.source_root, account_ref=args.account_ref)
            plain(args.bundle, missing=True)
            with args.bundle.open("xb") as handle:
                handle.write(canonical(bundle))
            print(json.dumps({"digest": bundle["digest"], "days": len(bundle["days"])}))
        else:
            plain(args.bundle)
            if args.bundle.stat().st_size > MAX_BUNDLE_BYTES:
                fail("provider_handoff_bundle_too_large")
            bundle = strict_json(args.bundle.read_bytes())
            print(
                json.dumps(
                    import_bundle(
                        bundle,
                        args.root,
                        expected_digest=args.digest,
                        account_ref=args.account_ref,
                        stopped_source_ref=args.stopped_source_ref,
                        dry_run=not args.apply,
                    )
                )
            )
    except (ProviderBudgetError, ValueError, KeyError, TypeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": exc.code if isinstance(exc, ProviderBudgetError) else "provider_handoff_invalid",
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
