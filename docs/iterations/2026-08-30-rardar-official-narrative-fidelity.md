# 2026-08-30 — Rardar Official Narrative Fidelity

## Goal

Preserve a repository author's mature README narrative before adding Rardar's
own assessment. Content-quality checks alone were not sufficient: Serving v4
could publish accurate prose while giving a derived core-value template more
visual and semantic authority than the author's tagline, positioning and
ordered highlight titles.

## Serving Narrative v5

Serving v5 separates the two layers while continuing to read Serving v1–v4:

- `officialTaglineZh` is the author's one-line project definition;
- `officialPositioningZh` is the complete opening product-positioning paragraph;
- `officialHighlights` preserves source title, detail, evidence and order;
- `officialNarrativeMode` records `official_zh`, `official_translated`,
  `rardar_derived` or `insufficient`;
- `officialNarrativeIssues` contains bounded stable degradation reasons;
- `rardarAssessmentZh` and `rardarDifferentiators` are explicitly Rardar's
  engineering and adoption judgments.

The legacy fields remain compatibility projections only:
`identitySummaryZh` maps to the official tagline, while `coreValueZh` and
`keyDifferentiators` map to the Rardar assessment layer. Schema validation
rejects incompatible projections, invalid source labels, reordered highlights
and unsafe insufficient profiles.

## Extraction and translation

The generic README parser inspects the narrative opening after the H1. It
recognizes a standalone emphasized tagline, the following prose paragraph and
continuous list items whose bold title is separated from its body. It records
source order and versioned evidence references without classifying or renaming
the author titles.

A mature Chinese README follows a deterministic zero-model path. A mature
English README is structured first and then translated through the existing
`routing_group=rardar` control plane. The translation contract requires the
same highlight count and order and rejects classification, marketing additions
and unsupported facts. Weak or failed source structures are explicitly labelled
`Rardar 整理`; unusable evidence exposes safe facts only.

Official translation and Rardar assessment use separate cache namespaces and
prompt versions. Cache identities include the evidence revision, Schema,
prompt versions and narrative mode. Neither path changes ranking facts.

## Product hierarchy and audit

Today presents repository, high-salience official tagline, source-labelled
positioning and the first two author-ordered highlights before objective Star
facts and actions. It never presents the Rardar assessment as official content.

Project detail presents the official tagline in the Hero, the official
positioning in the dark lead section and every author-ordered highlight in the
capability narrative. Rardar assessment and differentiators appear only in the
decision-and-adoption section. Provenance remains closed by default and records
the narrative mode, source, highlight count and assessment layer.

The read-only narrative audit validates every current Top 20 project and emits
stable violation codes for title rewriting, order changes, translation
count/order changes, false source labels and official/Rardar boundary leaks.
It performs no network or model calls.

## Boundaries

Normal Today and project-detail reads remain immutable static Serving reads:
zero GitHub calls, zero LLM calls and zero raw Artifact reads. This iteration
adds no database table or migration, changes no model route or credential, and
does not access Production. `RARDAR-DISCOVER-REALTIME-01` remains out of scope.

## Real-data acceptance

The isolated rebuild copied the local Runtime mirror before execution and left
its root pointer and raw generation byte-for-byte unchanged. Serving v5
`20260828T001104828269Z-aea4f42ac953--b916fed4c2f86ad0` was built from raw
generation `20260828T001104828269Z-aea4f42ac953`:

- 20/20 projects have Chinese summaries;
- 19 are quality-ready and one is explicitly partial;
- one project follows the zero-model `official_zh` path;
- one follows the ordered `official_translated` path;
- 18 weak-source profiles are explicitly labelled `rardar_derived`;
- none is rejected or marked `insufficient`.

The narrative audit and existing content audit both pass. Narrative violations
are zero for title rewriting, source order, translation count/order and
official/Rardar boundary leakage. The content audit reports zero unsafe URLs,
redirect prose, long untranslated English passages, placeholders, empty core
values, duplicate capabilities or evidence failures.

The Archify gold sample preserves its Chinese tagline and complete positioning,
followed by the exact four author titles in order: “打开就是成品”,
“合并前先看清架构变化”, “每次探索都有依据” and “一个文件即可放心交付”.
Its Rardar assessment and comparison dimensions remain in a separate section.
Manual checks also covered seven other current projects, an ordered mature
English README and a weak-source README.

## Verification

- backend: 895 passed, 3 skipped; fresh and repeated migrations passed;
- frontend: 202/202 Vitest tests passed with statement and branch coverage
  above 90%; TypeScript and production build passed;
- Python Ruff lint, changed-file format check, layering, `pip check` and
  `pip-audit` passed;
- the Rardar build and npm security audit passed with zero vulnerabilities;
- isolated production HTTP p95 was 11.79 ms for Today API, 28.37 ms for Today,
  10.36 ms for project detail and 1.42 ms for health;
- repeated Today, detail and Find reads created zero LLM calls, analysis jobs,
  feedback or content rows, and the backend retained no external connection;
- 375, 768 and 1440 pixel Today layouts plus official Chinese, translated
  English and weak-source detail pages were visually inspected.

Repository-wide Ruff format and frontend ESLint still report unrelated
pre-existing baseline debt (478 Python files would be reformatted; frontend
reports 24 errors and 218 warnings). Changed Python and frontend files pass
their scoped format/lint checks. No baseline file was mechanically rewritten.
