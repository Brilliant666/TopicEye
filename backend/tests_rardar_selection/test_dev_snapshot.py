"""Saved public snapshot isolation tests: no SSH, DB or model execution."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/rardar_dev_snapshot.py"
spec = importlib.util.spec_from_file_location("dev_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_public_export_and_install(tmp_path):
    source = tmp_path / "source"
    (source / "trending-boards").mkdir(parents=True)
    (source / "historical-daily").mkdir()
    (source / "trending-boards/current.json").write_text('{"generationId":"saved"}')
    (source / "historical-daily/2026-09-14.json").write_text('{"items":[1,2,3,4,5,6,7,8]}')
    (source / "trending-boards/material-work.json").write_text('{"pending":true}')
    (source / "secret.json").write_text('{"password":"fixture"}')
    archive = tmp_path / "public.tar"
    with archive.open("wb") as output:
        module.export_saved(source, output)
    target = tmp_path / "dev"
    final = module.install_snapshot(archive, target)
    assert (final / "historical-daily/2026-09-14.json").exists()
    assert not (final / "trending-boards/material-work.json").exists()
    assert not (final / "secret.json").exists()
    assert json.loads((target / "current.json").read_text())["snapshot"] == final.name


@pytest.mark.parametrize(
    "name",
    ["../private.json", "trending-boards/../../secret.json", "budget/ledger.json", "project-insights/../../key.json"],
)
def test_bad_archive_preserves_pointer(tmp_path, name):
    target = tmp_path / "dev"
    target.mkdir()
    pointer = '{"schemaVersion":1,"snapshot":"previous","exportedAt":"yesterday"}'
    (target / "current.json").write_text(pointer)
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as output:
        info = tarfile.TarInfo(name)
        info.size = 2
        output.addfile(info, io.BytesIO(b"{}"))
    with pytest.raises(ValueError):
        module.install_snapshot(archive, target)
    assert (target / "current.json").read_text() == pointer


def test_remote_program_is_valid_and_has_no_main(tmp_path):
    program = SCRIPT.read_text().rsplit('\nif __name__ == "__main__":', 1)[0]
    compile(program + "\nexport_saved(Path(SOURCE), sys.stdout.buffer)\n", "remote", "exec")


def test_production_pointer_refused(tmp_path):
    (tmp_path / "current.json").write_text('{"generationId":"production"}')
    with pytest.raises(ValueError, match="not a development"):
        module.install_snapshot(tmp_path / "absent.tar", tmp_path)


def test_digest_failure_preserves_previous(tmp_path):
    archive = tmp_path / "corrupt.tar"
    manifest = {
        "schemaVersion": 1,
        "sourceRoot": module.SOURCE,
        "sourceSite": "https://rardar.cosflow.icu",
        "exportedAt": "saved",
        "files": {"trending-boards/current.json": {"sha256": "0" * 64, "bytes": 2, "sourceMtimeNs": 1}},
    }
    with tarfile.open(archive, "w") as output:
        for name, raw in [
            ("trending-boards/current.json", b"{}"),
            ("snapshot-manifest.json", json.dumps(manifest).encode()),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            output.addfile(info, io.BytesIO(raw))
    with pytest.raises(ValueError, match="digest mismatch"):
        module.install_snapshot(archive, tmp_path / "dev")
    assert not (tmp_path / "dev/current.json").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_link_archive_rejected(tmp_path, kind):
    archive = tmp_path / "link.tar"
    with tarfile.open(archive, "w") as output:
        info = tarfile.TarInfo("trending-boards/current.json")
        info.type = kind
        info.linkname = "/etc/shadow"
        output.addfile(info)
    with pytest.raises(ValueError, match="unsafe archive"):
        module.install_snapshot(archive, tmp_path / "dev")
