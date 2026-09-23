#!/usr/bin/env bash
# Artifact-only CI entry: no application startup, credentials, source data or deploy.
set -euo pipefail
[[ "${SOURCE_SHA:-}" =~ ^[0-9a-f]{40}$ ]]
test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
test -z "$(git status --porcelain)"
: "${RUNNER_TEMP:?This entry requires an isolated runner temp directory}"
OUT="$RUNNER_TEMP/rardar-release-output"
CONTEXT="$RUNNER_TEMP/rardar-release-source"
test ! -e "$OUT"
test ! -e "$CONTEXT"
mkdir -p "$OUT" "$CONTEXT"
# Only tracked exact-source bytes; no operator filesystem or local env files.
git archive "$SOURCE_SHA" | tar --exclude='backend/.env.production' -x -C "$CONTEXT"
# Tracked deployment configuration is excluded before extraction, never read.
printf '%s\n' 'backend/.env.production' > "$OUT/excluded-source-inputs.txt"
if find "$CONTEXT/frontend" "$CONTEXT/backend" -type f \
  \( -name '.env' -o -name '.env.*' -o -name '*.sqlite' \
     -o -name '*.sqlite3' -o -name '*.db' \) ! -name '.env.example' | grep -q .; then
  echo 'Forbidden environment/database input in source context' >&2
  exit 1
fi
FRONTEND="rardar-frontend:$SOURCE_SHA"
BACKEND="rardar-backend:$SOURCE_SHA"
# Pin floating FROM tags to the resolved digest in this isolated build context.
# This changes no source file and records the exact resolved inputs below.
docker pull --platform linux/amd64 node:20-alpine
docker pull --platform linux/amd64 python:3.12-slim
NODE_BASE="$(docker image inspect node:20-alpine --format '{{index .RepoDigests 0}}')"
PYTHON_BASE="$(docker image inspect python:3.12-slim --format '{{index .RepoDigests 0}}')"
sed -i "s|^FROM node:20-alpine$|FROM $NODE_BASE|" "$CONTEXT/frontend/Dockerfile"
sed -i "s|^FROM python:3.12-slim|FROM $PYTHON_BASE|" "$CONTEXT/backend/Dockerfile"
printf '%s\n%s\n' "$NODE_BASE" "$PYTHON_BASE" > "$OUT/base-images.txt"
docker image inspect node:20-alpine python:3.12-slim > "$OUT/base-images.json"
sha256sum "$CONTEXT/frontend/Dockerfile" "$CONTEXT/backend/Dockerfile" > "$OUT/resolved-dockerfiles.sha256"
docker buildx build --platform linux/amd64 --load --progress plain \
  --metadata-file "$OUT/backend-build.json" --tag "$BACKEND" "$CONTEXT/backend"
docker buildx build --platform linux/amd64 --load --progress plain \
  --build-arg RARDAR_PRODUCT_MODE=true --build-arg BACKEND_API_URL=http://backend:8000 \
  --metadata-file "$OUT/frontend-build.json" --tag "$FRONTEND" "$CONTEXT/frontend"
docker image inspect "$BACKEND" "$FRONTEND" > "$OUT/images.json"
# Python runtime intentionally has no pip. Record freeze-equivalent inventory,
# then verify installed dependency requirements without network or app startup.
docker run --rm --network none --entrypoint python "$BACKEND" -c \
  'from importlib.metadata import distributions; print("\n".join(sorted(d.metadata["Name"]+"=="+d.version for d in distributions())))' \
  > "$OUT/python-freeze.txt"
docker run --rm -i --network none --entrypoint python "$BACKEND" <<'PY'
import importlib.util
import ast
from pathlib import Path
from importlib.metadata import distributions, version, PackageNotFoundError
from packaging.requirements import Requirement
import fastapi, sqlalchemy, asyncpg, duckdb, pydantic
for module in ('scripts.rebuild_rardar_serving', 'scripts.rebuild_rardar_discover_selection',
               'scripts.reassemble_rardar_profile_cache', 'scripts.correct_rardar_material_once'):
    assert importlib.util.find_spec(module), module
ast.parse(Path('app/services/llm/provider_budget_handoff.py').read_text())
issues = []
for line in Path('requirements.txt').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    req = Requirement(line)
    try:
        if req.specifier and not req.specifier.contains(version(req.name), prereleases=True):
            issues.append(f'direct requirement: {req.name} incompatible')
    except PackageNotFoundError:
        issues.append(f'direct requirement: {req.name} missing')
for dist in distributions():
    for text in dist.requires or []:
        req = Requirement(text)
        if req.marker and not req.marker.evaluate({'extra': ''}):
            continue
        try:
            installed = version(req.name)
            if req.specifier and not req.specifier.contains(installed, prereleases=True):
                issues.append(f'{dist.metadata["Name"]}: {req.name} incompatible')
        except PackageNotFoundError:
            issues.append(f'{dist.metadata["Name"]}: {req.name} missing')
assert not issues, issues
print('Runtime package dependency and script presence checks: PASS')
PY
docker run --rm --network none --entrypoint node "$FRONTEND" -e \
  'const a=require("node:assert/strict"); const c=require("./.next/required-server-files.json").config; a.equal(c.env.NEXT_PUBLIC_RARDAR_PRODUCT_MODE,"true"); const r=require("./.next/routes-manifest.json").rewrites; a(r.beforeFiles.some(x=>x.source==="/"&&x.destination==="/rardar-foundation")); a(r.afterFiles.some(x=>x.source==="/api/:path*"&&x.destination==="http://backend:8000/api/:path*")); console.log("Compiled Rardar profile and rewrite: PASS")'
docker run --rm --network none --entrypoint sh "$BACKEND" -c 'python --version; uname -m; cat /etc/os-release' > "$OUT/backend-platform.txt"
docker run --rm --network none --entrypoint sh "$FRONTEND" -c 'node --version; npm --version; uname -m; cat /etc/os-release' > "$OUT/frontend-platform.txt"
export OUT
python3 - <<'PY'
import hashlib, json, os, pathlib, subprocess
out = pathlib.Path(os.environ['OUT'])
images = json.loads((out / 'images.json').read_text())
assert all(i['Os'] == 'linux' and i['Architecture'] == 'amd64' for i in images)
files = ['frontend/package-lock.json', 'backend/requirements.txt', 'frontend/Dockerfile', 'backend/Dockerfile', 'backend/.dockerignore']
manifest = {
    'schemaVersion': 1, 'sourceSha': os.environ['SOURCE_SHA'],
    'sourceTree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'repository': os.environ.get('GITHUB_REPOSITORY'),
    'buildRunId': os.environ.get('GITHUB_RUN_ID'),
    'platform': 'linux/amd64', 'buildArgs': {'RARDAR_PRODUCT_MODE': 'true', 'BACKEND_API_URL': 'http://backend:8000'},
    'inputSha256': {f: hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in files},
    'images': [{'id': i['Id'], 'repoDigests': i.get('RepoDigests', []), 'tags': i['RepoTags'], 'bytes': i['Size']} for i in images],
    'baseDigests': (out / 'base-images.txt').read_text().splitlines(),
    'pythonInventory': 'python-freeze.txt (importlib.metadata; runtime pip removed)',
    'fullyLockedDependencies': False, 'productionDataIncluded': False,
    'excludedTrackedInputs': ['backend/.env.production'],
    'deployed': False, 'modelCalls': 0,
}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
docker save "$BACKEND" "$FRONTEND" | gzip -1 > "$OUT/images.tar.gz"
(cd "$OUT" && sha256sum images.tar.gz manifest.json > SHA256SUMS)
