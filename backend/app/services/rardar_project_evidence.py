"""Bounded, read-only GitHub evidence for one on-demand Rardar project insight."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

_README_MAX_CHARS = 12_000
_README_RESPONSE_MAX_BYTES = 1_500_000
_TREE_MAX_ITEMS = 100
_CACHE_TTL_SECONDS = 900
_CACHE_MAX_ENTRIES = 256
_MANIFESTS = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "composer.json",
    "gemfile",
    "dockerfile",
    "docker-compose.yml",
    "compose.yml",
}
_CHINESE = re.compile(r"[\u3400-\u9fff]")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_CACHE: dict[tuple[str, str], tuple[float, ProjectEvidence]] = {}


@dataclass(frozen=True)
class ProjectEvidence:
    payload: dict[str, Any]
    digest: str
    allowed_refs: frozenset[str]
    path_refs: dict[str, str]
    official_intro: dict[str, Any]
    expected_intro_label: str
    cache_hit: bool


def clear_project_evidence_cache() -> None:
    _CACHE.clear()


def _clean_markdown(value: str, maximum: int) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"!\[[^]]*]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_~]", "", value)
    return re.sub(r"\s+", " ", value).strip()[:maximum]


def _readme_summary(markdown: str) -> tuple[str | None, list[dict[str, str]]]:
    headings: list[dict[str, str]] = []
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for raw_line in markdown[:_README_MAX_CHARS].splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            if current:
                paragraphs.append(_clean_markdown(" ".join(current), 1200))
                current = []
            label = _clean_markdown(heading.group(1), 160)
            if label and len(headings) < 20:
                headings.append({"title": label, "ref": f"readme:heading:{len(headings) + 1}"})
            continue
        if not line:
            if current:
                paragraphs.append(_clean_markdown(" ".join(current), 1200))
                current = []
            continue
        if line.startswith(("[![", "![", "<img", "<picture", "|", "---", "***")):
            continue
        if len(line) < 18 and line.startswith(("-", "*", "+")):
            continue
        current.append(line)
    if current:
        paragraphs.append(_clean_markdown(" ".join(current), 1200))
    introduction = next((item for item in paragraphs if len(item) >= 24), None)
    return introduction, headings


def _preferred_chinese_readme(items: list[dict[str, str]]) -> str | None:
    candidates: list[str] = []
    for item in items:
        if item["type"] != "file":
            continue
        name = item["path"].lower()
        stem, separator, suffix = name.rpartition(".")
        if not separator or suffix not in {"md", "markdown"} or not stem.startswith("readme"):
            continue
        tokens = {token for token in re.split(r"[._-]+", stem) if token}
        if tokens & {"zh", "zhcn", "cn", "chs", "chinese"}:
            candidates.append(item["path"])
    return sorted(candidates, key=lambda value: (len(value), value.lower()))[0] if candidates else None


def _readme_heading_path(readme_path: str, title: str, occurrences: dict[str, int]) -> str:
    anchor = re.sub(r"[^\w\u3400-\u9fff -]", "", title.lower(), flags=re.UNICODE)
    anchor = re.sub(r"\s+", "-", anchor).strip("-")
    if not anchor:
        return readme_path
    count = occurrences.get(anchor, 0)
    occurrences[anchor] = count + 1
    return f"{readme_path}#{anchor}{f'-{count}' if count else ''}"


def _json_object(response: httpx.Response) -> dict[str, Any] | None:
    if len(response.content) > _README_RESPONSE_MAX_BYTES:
        return None
    try:
        value = response.json()
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def _get(client: httpx.AsyncClient, path: str) -> httpx.Response | None:
    try:
        response = await client.get(path)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response
    except httpx.HTTPError:
        return None


def _canonical_digest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def collect_project_evidence(
    repository: str,
    artifact_facts: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> ProjectEvidence:
    """Collect at most four public GitHub API responses; never clone or execute code."""

    revision = _canonical_digest(
        {
            "repository": repository,
            "description": artifact_facts.get("description"),
            "pushedAt": artifact_facts.get("pushedAt"),
            "licenseSpdxId": artifact_facts.get("licenseSpdxId"),
        }
    )
    cache_key = (repository.lower(), revision)
    now = time.monotonic()
    for key, (created_at, _) in list(_CACHE.items()):
        if now - created_at > _CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
    cached = _CACHE.get(cache_key)
    if cached:
        value = cached[1]
        return ProjectEvidence(**{**value.__dict__, "cache_hit": True})

    owned = client is None
    if client is None:
        client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "TopicEye-Rardar/1.0"},
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            trust_env=True,
        )
    metadata: dict[str, Any] = {}
    readme_text: str | None = None
    readme_path: str | None = None
    tree_items: list[dict[str, str]] = []
    release: dict[str, Any] | None = None
    try:
        metadata_response = await _get(client, f"/repos/{repository}")
        if metadata_response:
            metadata = _json_object(metadata_response) or {}

        tree_response = await _get(client, f"/repos/{repository}/contents")
        if tree_response and len(tree_response.content) <= _README_RESPONSE_MAX_BYTES:
            try:
                tree_payload = tree_response.json()
            except ValueError:
                tree_payload = []
            if isinstance(tree_payload, list):
                for item in tree_payload[:_TREE_MAX_ITEMS]:
                    if not isinstance(item, dict):
                        continue
                    path = item.get("path")
                    kind = item.get("type")
                    if isinstance(path, str) and isinstance(kind, str) and len(path) <= 240:
                        tree_items.append({"path": path, "type": kind})

        preferred_readme = _preferred_chinese_readme(tree_items)
        readme_endpoint = (
            f"/repos/{repository}/contents/{quote(preferred_readme, safe='')}"
            if preferred_readme
            else f"/repos/{repository}/readme"
        )
        readme_response = await _get(client, readme_endpoint)
        readme_payload = _json_object(readme_response) if readme_response else None
        if (
            readme_payload
            and readme_payload.get("encoding") in {None, "base64"}
            and isinstance(readme_payload.get("content"), str)
        ):
            try:
                decoded = base64.b64decode(readme_payload["content"], validate=False).decode("utf-8", errors="replace")
                readme_text = decoded[:_README_MAX_CHARS]
                payload_path = readme_payload.get("path")
                readme_path = (
                    payload_path if isinstance(payload_path, str) and len(payload_path) <= 240 else preferred_readme
                )
                if not readme_path:
                    readme_path = "README.md"
            except (ValueError, UnicodeError):
                readme_text = None
                readme_path = None

        release_response = await _get(client, f"/repos/{repository}/releases/latest")
        if release_response:
            release = _json_object(release_response)
    finally:
        if owned:
            await client.aclose()

    description = metadata.get("description") if isinstance(metadata.get("description"), str) else None
    if not description:
        description = artifact_facts.get("description") if isinstance(artifact_facts.get("description"), str) else None
    introduction, headings = _readme_summary(readme_text or "")
    allowed_refs = {"repository"}
    evidence_index: dict[str, str] = {"repository": repository}
    path_refs: dict[str, str] = {}
    if description:
        allowed_refs.add("description")
        evidence_index["description"] = description[:1000]
    if introduction:
        allowed_refs.add("readme:introduction")
        evidence_index["readme:introduction"] = f"{readme_path}: {introduction}" if readme_path else introduction
        if readme_path:
            path_refs["readme:introduction"] = readme_path
    heading_occurrences: dict[str, int] = {}
    for heading in headings:
        allowed_refs.add(heading["ref"])
        if readme_path:
            heading_path = _readme_heading_path(readme_path, heading["title"], heading_occurrences)
            heading["path"] = heading_path
            path_refs[heading["ref"]] = heading_path
            evidence_index[heading["ref"]] = f"{heading_path}: {heading['title']}"
        else:
            evidence_index[heading["ref"]] = heading["title"]

    for item in tree_items:
        prefix = "file" if item["type"] == "file" else "tree"
        reference = f"{prefix}:{item['path']}"
        allowed_refs.add(reference)
        evidence_index[reference] = f"{item['type']}: {item['path']}"
        path_refs[reference] = item["path"]
    manifests = [item["path"] for item in tree_items if item["path"].lower() in _MANIFESTS]

    license_id = metadata.get("license", {}).get("spdx_id") if isinstance(metadata.get("license"), dict) else None
    if not isinstance(license_id, str) or license_id == "NOASSERTION":
        license_id = artifact_facts.get("licenseSpdxId")
    if isinstance(license_id, str):
        allowed_refs.add("license")
        evidence_index["license"] = license_id

    release_summary = None
    if release:
        release_name = release.get("name") or release.get("tag_name")
        if isinstance(release_name, str):
            release_summary = {
                "name": release_name[:200],
                "publishedAt": release.get("published_at") if isinstance(release.get("published_at"), str) else None,
                "body": _clean_markdown(release.get("body") or "", 600),
            }
            allowed_refs.add("release:latest")
            evidence_index["release:latest"] = json.dumps(release_summary, ensure_ascii=False)
            path_refs["release:latest"] = "Releases"

    if introduction and _CHINESE.search(introduction):
        official_intro = {"text": introduction, "sourceLabel": "官方介绍", "evidenceRefs": ["readme:introduction"]}
        expected_intro_label = "官方介绍"
    elif description and _CHINESE.search(description):
        official_intro = {"text": description[:600], "sourceLabel": "官方介绍", "evidenceRefs": ["description"]}
        expected_intro_label = "官方介绍"
    elif description:
        official_intro = {"text": description[:600], "sourceLabel": "官方介绍", "evidenceRefs": ["description"]}
        expected_intro_label = "官方介绍（译）"
    elif introduction:
        official_intro = {
            "text": introduction[:600],
            "sourceLabel": "官方介绍",
            "evidenceRefs": ["readme:introduction"],
        }
        expected_intro_label = "官方介绍（译）"
    else:
        official_intro = {
            "text": "官方资料暂未提供可验证的项目简介。",
            "sourceLabel": "AI受限概括",
            "evidenceRefs": ["repository"],
        }
        expected_intro_label = "AI受限概括"

    payload = {
        "repository": repository,
        "description": description,
        "readme": {"path": readme_path, "introduction": introduction, "headings": headings},
        "topLevelTree": tree_items,
        "packageManifests": manifests,
        "metadata": {
            "primaryLanguage": metadata.get("language") or artifact_facts.get("primaryLanguage"),
            "topics": metadata.get("topics") or artifact_facts.get("topics") or [],
            "licenseSpdxId": license_id,
            "pushedAt": metadata.get("pushed_at") or artifact_facts.get("pushedAt"),
            "archived": bool(metadata.get("archived", artifact_facts.get("archived", False))),
            "disabled": bool(metadata.get("disabled", False)),
        },
        "latestRelease": release_summary,
        "evidenceIndex": evidence_index,
        "collectionLimits": {
            "githubRequests": 4,
            "readmeChars": _README_MAX_CHARS,
            "treeItems": _TREE_MAX_ITEMS,
            "releaseCount": 1,
            "timeoutSeconds": 8,
        },
    }
    value = ProjectEvidence(
        payload=payload,
        digest=_canonical_digest(payload),
        allowed_refs=frozenset(allowed_refs),
        path_refs=path_refs,
        official_intro=official_intro,
        expected_intro_label=expected_intro_label,
        cache_hit=False,
    )
    while len(_CACHE) >= _CACHE_MAX_ENTRIES:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = (time.monotonic(), value)
    return value
