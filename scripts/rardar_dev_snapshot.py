"""On-demand saved public Rardar material snapshot; never executes business jobs.

The SSH account must already be authorized for the existing root file-read
entry. This command never exports PostgreSQL or credentials/ledgers.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys  # noqa: F401 - used by the appended remote export entry point
import tarfile
import tempfile
from datetime import datetime, timezone

SOURCE = "/var/lib/rardar-product/intelligence"
STORES = frozenset(("trending-boards", "historical-daily", "profile-cache",
    "selection-profile-cache", "discover-profile-cache", "project-insights",
    "public-project-evidence", "serving", "generations"))
EXCLUDED = frozenset(("daily-refresh", "material-work.json", "profile-attempts",
    "writer.lock", "interactive-waiters"))
MAX_BYTES = 2 * 1024**3
MAX_FILE = 64 * 1024**2


def allowed(name: str) -> bool:
    if name == "current.json":
        return True
    parts = PurePosixPath(name).parts
    return bool(parts and not name.startswith("/") and "\\" not in name
        and all(p not in (".", "..", "") for p in name.split("/"))
        and parts[0] in STORES and name.endswith(".json")
        and not any(p in EXCLUDED or p.endswith(".lock") for p in parts))


def plain_chain(path: Path) -> None:
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("unsafe path")


def signature(path: Path) -> tuple:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
        raise ValueError("unsafe source file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def export_saved(root: Path, output) -> None:
    plain_chain(root)
    files = {}
    if (root / "current.json").exists():
        files["current.json"] = signature(root / "current.json")
    for store in sorted(STORES):
        directory = root / store
        if not directory.exists():
            continue
        plain_chain(directory)
        for current, dirs, names in os.walk(directory, followlinks=False):
            for child in dirs:
                plain_chain(Path(current) / child)
            dirs[:] = [x for x in dirs if x not in EXCLUDED]
            for name in names:
                path = Path(current) / name
                relative = path.relative_to(root).as_posix()
                if allowed(relative):
                    files[relative] = signature(path)
    if not files or sum(v[2] for v in files.values()) > MAX_BYTES:
        raise ValueError("empty or oversized source")
    manifest = {"schemaVersion": 1, "sourceRoot": SOURCE,
        "sourceSite": "https://rardar.cosflow.icu", "exportedAt": datetime.now(timezone.utc).isoformat(),
        "files": {}}
    with tarfile.open(fileobj=output, mode="w|") as archive:
        for relative, before in sorted(files.items()):
            path = root / relative
            raw = path.read_bytes()
            if signature(path) != before or len(raw) != before[2]:
                raise ValueError("source changed")
            json.loads(raw)
            manifest["files"][relative] = {"sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw), "sourceMtimeNs": before[3]}
            info = tarfile.TarInfo(relative)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
        # Recheck all selected files, especially current pointers, before commit.
        if any(signature(root / name) != before for name, before in files.items()):
            raise ValueError("source changed during export")
        raw = json.dumps(manifest, sort_keys=True).encode()
        info = tarfile.TarInfo("snapshot-manifest.json")
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))


def install_snapshot(archive_path: Path, destination: Path) -> Path:
    plain_chain(destination)
    destination.mkdir(parents=True, exist_ok=True)
    pointer_path = destination / "current.json"
    plain_chain(pointer_path)
    if pointer_path.exists():
        old = json.loads(pointer_path.read_text(encoding="utf-8"))
        if set(old) != {"schemaVersion", "snapshot", "exportedAt"} or old["schemaVersion"] != 1:
            raise ValueError("destination is not a development snapshot store")
    stage = Path(tempfile.mkdtemp(prefix=".incoming-", dir=destination))
    try:
        seen = {}
        manifest = None
        total = 0
        with tarfile.open(archive_path, "r|") as archive:
            for member in archive:
                if not member.isfile() or member.name in seen or member.size > MAX_FILE:
                    raise ValueError("unsafe archive member")
                total += member.size
                if total > MAX_BYTES:
                    raise ValueError("oversized archive")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError("missing file")
                raw = handle.read(MAX_FILE + 1)
                if len(raw) != member.size:
                    raise ValueError("truncated file")
                if member.name == "snapshot-manifest.json":
                    if manifest is not None:
                        raise ValueError("duplicate manifest")
                    manifest = json.loads(raw)
                    continue
                if not allowed(member.name):
                    raise ValueError("nonpublic archive member")
                json.loads(raw)
                seen[member.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        if not isinstance(manifest, dict) or set(manifest) != {"schemaVersion", "sourceRoot", "sourceSite", "exportedAt", "files"}:
            raise ValueError("invalid manifest")
        if manifest["schemaVersion"] != 1 or manifest["sourceRoot"] != SOURCE or manifest["sourceSite"] != "https://rardar.cosflow.icu":
            raise ValueError("source mismatch")
        if set(manifest["files"]) != set(seen) or not seen:
            raise ValueError("inventory mismatch")
        for name, value in manifest["files"].items():
            if set(value) != {"sha256", "bytes", "sourceMtimeNs"} or any(value[k] != v for k, v in seen[name].items()):
                raise ValueError("digest mismatch")
        raw = json.dumps(manifest, sort_keys=True).encode()
        identifier = hashlib.sha256(raw).hexdigest()
        (stage / "snapshot-manifest.json").write_bytes(raw)
        final = destination / identifier
        if final.exists():
            raise ValueError("snapshot already exists; refusing overwrite")
        os.replace(stage, final)
        pointer = destination / ".current.tmp"
        with pointer.open("x", encoding="utf-8") as stream:
            json.dump({"schemaVersion": 1, "snapshot": identifier, "exportedAt": manifest["exportedAt"]}, stream)
        os.replace(pointer, destination / "current.json")
        return final
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if not args.destination.is_absolute():
        parser.error("destination must be an absolute independent development snapshot directory")
    plain_chain(args.destination)
    args.destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".transfer-", dir=args.destination) as temporary:
        archive = Path(temporary) / "public.tar"
        # Existing approved root file-read entry, fixed public root/allowlist.
        # No SQL, environment loading, network fetching or model calls.
        program = Path(__file__).read_text(encoding="utf-8").rsplit('\nif __name__ == "__main__":', 1)[0]
        program += '\nexport_saved(Path(SOURCE), sys.stdout.buffer)\n'
        with archive.open("wb") as output:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=15", "rardar-prod", "sudo -n /usr/bin/python3 -I -"], input=program.encode(),
                stdout=output, stderr=subprocess.PIPE, timeout=600, check=False)
        if result.returncode:
            raise RuntimeError("remote public snapshot failed; previous snapshot preserved")
        final = install_snapshot(archive, args.destination)
        print(json.dumps({"status": "saved", "path": str(final), "productionWrites": 0}))


if __name__ == "__main__":
    main()
