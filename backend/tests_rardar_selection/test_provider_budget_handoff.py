import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.services.llm.provider_budget import DAILY_TASK_ID, ProviderBudgetError, ProviderBudgetLedger, canonical
from app.services.llm.provider_budget_handoff import FILES, export_bundle, import_bundle


def source(tmp_path):
    root = tmp_path / "source"
    ledger = ProviderBudgetLedger.initialize(
        root / "2026-09-13" / FILES[0], "daily-2026-09-13", task_id=DAILY_TASK_ID, limit=100
    )
    with ledger.execution("project_profile"):
        pass
    with pytest.raises(RuntimeError), ledger.execution("project_profile"):
        raise RuntimeError("fake failure")
    ledger.record("reserved", "project_profile")  # Interrupted before dispatch: never refunded.
    attempt = ledger.record("reserved", "project_profile")
    ledger.record("dispatched", "project_profile", attempt)  # Unknown upstream outcome.
    ProviderBudgetLedger.initialize(root / "2026-09-14" / FILES[0], "daily-2026-09-14", task_id=DAILY_TASK_ID, limit=90)
    return root, ledger


def test_roundtrip_preserves_all_days_chain_and_inflight(tmp_path):
    root, ledger = source(tmp_path)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    bundle = export_bundle(root, source_root=str(root), account_ref="verified-account-test")
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    target = tmp_path / "target"
    kwargs = {"expected_digest": bundle["digest"], "account_ref": "verified-account-test"}
    assert import_bundle(bundle, target, **kwargs)["status"] == "dry_run"
    assert not target.exists()
    with pytest.raises(ProviderBudgetError):
        import_bundle(bundle, target, **kwargs, dry_run=False)
    assert not target.exists()
    import_bundle(bundle, target, **kwargs, stopped_source_ref="operator-stop-test", dry_run=False)
    resumed = ProviderBudgetLedger(target / "2026-09-13" / FILES[0], ledger.run_id, task_id=DAILY_TASK_ID, limit=100)
    assert resumed.events.read_bytes() == ledger.events.read_bytes()
    assert resumed.snapshot() == ledger.snapshot()
    assert resumed.snapshot()["reserved"] == 4
    with resumed.execution("project_profile"):
        pass
    # Re-import never replaces a newer target tail, or adds the source count twice.
    assert import_bundle(bundle, target, **kwargs, dry_run=False)["status"] == "already_imported"
    assert resumed.snapshot()["reserved"] == 5
    restarted = ProviderBudgetLedger(resumed.path, resumed.run_id, task_id=DAILY_TASK_ID, limit=100)
    assert restarted.snapshot()["reserved"] == 5
    tomorrow = ProviderBudgetLedger(
        target / "2026-09-14" / FILES[0], "daily-2026-09-14", task_id=DAILY_TASK_ID, limit=90
    )
    with tomorrow.execution("project_profile"):
        pass
    assert tomorrow.snapshot()["reserved"] == 1
    assert restarted.snapshot()["reserved"] == 5


def test_mismatch_digest_account_and_divergent_existing_fail(tmp_path):
    root, _ = source(tmp_path)
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    target = tmp_path / "target"
    with pytest.raises(ProviderBudgetError, match="digest_mismatch"):
        import_bundle(bundle, target, expected_digest="bad", account_ref="account-a")
    with pytest.raises(ProviderBudgetError, match="account_mismatch"):
        import_bundle(bundle, target, expected_digest=bundle["digest"], account_ref="account-b")
    target.mkdir()
    with pytest.raises(ProviderBudgetError):
        import_bundle(bundle, target, expected_digest=bundle["digest"], account_ref="account-a")


def test_copy_can_validate_original_windows_path_without_fake_windows_tree(tmp_path):
    root, _ = source(tmp_path)
    source_root = r"C:\Users\operator\daily-provider-budget\identity"
    for day in ("2026-09-13", "2026-09-14"):
        registration = root / day / FILES[2]
        value = json.loads(registration.read_bytes())
        value["path"] = source_root + "\\" + day + "\\" + FILES[0]
        registration.write_bytes(canonical(value))
    bundle = export_bundle(root, source_root=source_root, account_ref="account-a")
    assert len(bundle["days"]) == 2
    with pytest.raises(ProviderBudgetError, match="identity_mismatch"):
        export_bundle(root, source_root=str(root), account_ref="account-a")


def test_source_change_and_partial_or_tampered_input_rejected(tmp_path, monkeypatch):
    from app.services.llm import provider_budget_handoff as module

    root, ledger = source(tmp_path)
    original = module.inventory
    calls = []

    def changing(path):
        result = original(path)
        if not calls:
            ledger.record("reserved", "project_profile")
        calls.append(True)
        return result

    monkeypatch.setattr(module, "inventory", changing)
    with pytest.raises(ProviderBudgetError, match="source_changed"):
        export_bundle(root, source_root=str(root), account_ref="account-a")
    monkeypatch.setattr(module, "inventory", original)
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    broken = copy.deepcopy(bundle)
    broken["days"]["2026-09-13"]["summary"]["reserved"] = 0
    with pytest.raises(ProviderBudgetError):
        import_bundle(broken, tmp_path / "target", expected_digest=bundle["digest"], account_ref="account-a")
    ledger.events.write_bytes(ledger.events.read_bytes()[:-1])
    with pytest.raises(ProviderBudgetError):
        export_bundle(root, source_root=str(root), account_ref="account-a")


def test_stale_snapshot_is_preserved_and_replayed_without_refund(tmp_path):
    root, ledger = source(tmp_path)
    saved = ledger.path.read_bytes()
    ledger.record("reserved", "project_profile")
    ledger.path.write_bytes(saved)  # journal fsync succeeded, snapshot replace interrupted
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    assert bundle["days"]["2026-09-13"]["summary"]["reserved"] == 5
    target = tmp_path / "target"
    import_bundle(
        bundle,
        target,
        expected_digest=bundle["digest"],
        account_ref="account-a",
        stopped_source_ref="stop-evidence",
        dry_run=False,
    )
    migrated = ProviderBudgetLedger(target / "2026-09-13" / FILES[0], ledger.run_id, task_id=DAILY_TASK_ID, limit=100)
    assert migrated.path.read_bytes() == saved
    assert migrated.snapshot()["reserved"] == 5


def test_fork_never_merges_or_sums_consumption(tmp_path):
    root, ledger = source(tmp_path)
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    target = tmp_path / "target"
    kwargs = {"expected_digest": bundle["digest"], "account_ref": "account-a"}
    import_bundle(bundle, target, **kwargs, stopped_source_ref="stop-evidence", dry_run=False)
    # A second source keeps writing after export: neither same identity nor counts prove a single writer.
    ledger.record("reserved", "project_profile")
    newer = export_bundle(root, source_root=str(root), account_ref="account-a")
    with pytest.raises(ProviderBudgetError, match="target_conflict"):
        import_bundle(newer, target, expected_digest=newer["digest"], account_ref="account-a")
    # Even with the old receipt, a valid but independently initialized journal is not an extension.
    other = ProviderBudgetLedger.initialize(
        tmp_path / "other" / FILES[0], ledger.run_id, task_id=DAILY_TASK_ID, limit=100
    )
    (target / "2026-09-13" / FILES[0]).write_bytes(other.path.read_bytes())
    (target / "2026-09-13" / FILES[1]).write_bytes(other.events.read_bytes())
    with pytest.raises(ProviderBudgetError, match="divergent_chain"):
        import_bundle(bundle, target, **kwargs)


@pytest.mark.parametrize("invalid", ["relative", "C:relative", "/safe/../escape", r"C:\safe\..\escape"])
def test_source_path_rejects_relative_or_escape(tmp_path, invalid):
    root, _ = source(tmp_path)
    with pytest.raises(ProviderBudgetError, match="source_path_invalid"):
        export_bundle(root, source_root=invalid, account_ref="account-a")


def test_hardlink_and_duplicate_json_fail_closed(tmp_path):
    from app.services.llm.provider_budget_handoff import strict_json

    root, ledger = source(tmp_path)
    with pytest.raises(ProviderBudgetError, match="duplicate_key"):
        strict_json(b'{"days":{},"days":{}}')
    os.link(ledger.path, tmp_path / "linked")
    with pytest.raises(ProviderBudgetError, match="unsafe_path"):
        export_bundle(root, source_root=str(root), account_ref="account-a")


@pytest.mark.parametrize("failure", ["receipt", "second_day"])
def test_partial_import_never_exposes_runtime_root(tmp_path, monkeypatch, failure):
    from app.services.llm import daily_provider_budget as daily

    root, _ = source(tmp_path)
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    home, data = tmp_path / "home", tmp_path / "runtime-data"
    data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(home))
    monkeypatch.setattr(daily.settings, "RARDAR_BUDGET_IDENTITY_DATA_DIR", str(data))
    identity = hashlib.sha256(str(data.absolute()).encode()).hexdigest()[:20]
    target = home / "TopicEye" / "daily-provider-budget" / identity
    target.parent.mkdir(parents=True)
    original_open = Path.open

    def interrupted(path, mode="r", *args, **kwargs):
        if mode == "xb" and (
            path.name == "provider-budget-handoff.json" if failure == "receipt" else path.parent.name == "2026-09-14"
        ):
            raise OSError("injected write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", interrupted)
    with pytest.raises(OSError, match="injected"):
        import_bundle(
            bundle,
            target,
            expected_digest=bundle["digest"],
            account_ref="account-a",
            stopped_source_ref="stop-test",
            dry_run=False,
        )
    assert not target.exists()
    # The real existing binding path cannot create/consume a fresh allowance on failure.
    with pytest.raises(ProviderBudgetError):
        daily.daily_root()
    with pytest.raises(ProviderBudgetError):
        daily.daily_ledger(100)
    stages = list(target.parent.glob(f".{identity}.handoff-*"))
    assert len(stages) == 1  # Forensics retained, not automatically cleaned.
    staged = ProviderBudgetLedger(
        stages[0] / "2026-09-13" / FILES[0], "daily-2026-09-13", task_id=DAILY_TASK_ID, limit=100
    )
    with pytest.raises(ProviderBudgetError):
        staged.record("reserved", "project_profile")  # Final-path registration rejects staging use too.


def test_atomic_publish_does_not_replace_competing_target(tmp_path, monkeypatch):
    from app.services.llm import provider_budget_handoff as module

    root, _ = source(tmp_path)
    bundle = export_bundle(root, source_root=str(root), account_ref="account-a")
    target = tmp_path / "target"
    original = module.publish_root

    def competing(staging, destination):
        destination.mkdir()
        return original(staging, destination)

    monkeypatch.setattr(module, "publish_root", competing)
    with pytest.raises((ProviderBudgetError, OSError)):
        import_bundle(
            bundle,
            target,
            expected_digest=bundle["digest"],
            account_ref="account-a",
            stopped_source_ref="stop-test",
            dry_run=False,
        )
    assert list(target.iterdir()) == []


@pytest.mark.parametrize(
    "name,is_dir", [("unrecognized-events.jsonl", False), ("unexpected", True), ("provider-budget.lock", True)]
)
def test_unknown_day_records_and_wrong_lock_type_rejected(tmp_path, name, is_dir):
    root, ledger = source(tmp_path)
    path = ledger.path.parent / name
    if path.exists():
        path.unlink()
    if is_dir:
        path.mkdir()
    else:
        path.write_text("unreconciled", encoding="utf-8")
    with pytest.raises(ProviderBudgetError, match="inventory_unknown"):
        export_bundle(root, source_root=str(root), account_ref="account-a")


def test_duplicate_event_keys_rejected_even_if_last_value_matches_digest(tmp_path):
    root, ledger = source(tmp_path)
    raw = ledger.events.read_bytes().replace(b'"sequence":1', b'"sequence":1,"sequence":1', 1)
    ledger.events.write_bytes(raw)
    with pytest.raises(ProviderBudgetError, match="duplicate_key"):
        export_bundle(root, source_root=str(root), account_ref="account-a")
