# 2026-08-26 — Rardar Intelligence Adapter

## Goal

Promote the smallest safe vertical slice from the TopicEye × Rardar POC: render Rardar's real, audited Explosion Artifact through a formal read-only integration while preserving default TopicEye behavior and all database facts.

## Baseline

- TopicEye main: `b244e255ef254d697e6cb70594b856565cb6c792`.
- Rardar fact contract: merge `cb92274d5c3d3f8f17ab7f87b708040cc3635620`.
- POC PR #1 was audited but not modified.
- Production, Sub2API, AI, Find Project, Rardar Runtime, and D1 were out of scope.

## Delivered boundary

- Backend-only `RARDAR_INTELLIGENCE_DATA_DIR`, active only behind the existing Rardar profile.
- No-follow, stable, bounded, duplicate-key-safe JSON reads across pointer, manifest, Explosion Artifact, and referenced source copies.
- Exact generation/hash/Schema/provenance/cross-file validation and stable 503 error codes.
- `GET /api/v1/rardar/explosion-board` with ready, warming, baseline-missing and not-published product states.
- Rardar Today UI for exact Top 5, up to three pending projects (including warming and missing-baseline states), coverage, update time and generation provenance.
- Explicit “AI 项目解释尚未接入” label; no AI fields or recomputed ranks.
- Exact vendored contracts with offline provenance checking.
- Two official A/B fictitious fixtures generated and audited by Rardar main.
- Dedicated Linux CI job for provenance and fail-closed Adapter behavior.

## Safety and persistence

The Adapter never reads a second pointer in one request, never falls back to flat or retained data, and never writes either repository. No TopicEye model, repository, Alembic revision or PostgreSQL table was added. Rardar page/API reads must leave a normalized database export byte-equivalent.

Negative controls cover missing/invalid configuration, duplicate and non-finite JSON, manifest state/digest, artifact hash/Schema/generation identity/rank, source hash/path/canonical payload digest, pointer and generation symlinks, Windows reparse/junction classification, same-length mutation, delete/recreate, and A/B switching without mixed responses.

## Validation record

The final local and GitHub results are recorded in the Draft PR. Required gates include:

- full PostgreSQL backend suite plus the isolated Adapter suite;
- Ruff, formatting, API layering, dependency checks and audits;
- frontend TypeScript, Vitest coverage, default and Rardar builds;
- real HTTP checks for all product/error states and pointer switching;
- responsive Chromium checks at 375, 768 and 1440 pixels;
- normalized PostgreSQL export before/after read-only requests;
- local RSS/latency/500-item parse snapshots, explicitly not capacity guarantees.

## Rollback and next work

Rollback is an application revert and restart. It requires no database migration and does not alter Rardar data.

This iteration does not complete AI explanations, the full Explosion Board page, Find Project, observer scheduling, deployment, or P2. The PR remains Draft for human review and must not be auto-merged.
