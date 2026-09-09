# Today fact-first publication

Scope: `RARDAR-TODAY-FACT-FIRST-PUBLISH-01`. No Discover selection, Find,
model configuration, or remote lifecycle changes.

## Contract

Serving v8 replaces the historical v7 all-Top20-material publication rule.
The complete authoritative ranked inventory, identities, exact observation
window, Star facts, source hashes, evidence bindings and safe paths remain
mandatory. Missing summaries, positioning, capabilities and failed translation
attempts are material diagnostics, not publication quotas. No member is removed
or replaced because material is missing.

The candidate builder independently retains valid evidence-bound fields and
isolates unsupported optional claims. Chinese summary can be null. An original
Description is a separately labelled fact, never a translated summary. Material
state is complete/partial/unavailable; these counts do not gate publication.
Existing v1–v7 snapshots keep their original validation contract. Damaged
published artifacts are still rejected, never repaired by the page reader.

## Operator entry

`python -m scripts.sync_rardar_intelligence --target <mirror>` and
`python -m scripts.rebuild_rardar_serving --target <mirror>` now use the real
collector and compatible caches without model generation by default. They do
not use the test-only `--offline` path. GitHub metadata/README retrieval may
still occur during an explicit build; ordinary page reads remain local-only.

Optional later enrichment uses the same entry with `--generate-profiles` and
the existing configured durable Provider budget. Discover's shared provider
default is unchanged. Enrichment produces a new immutable Serving revision for
the same factual generation; original observations and rankings do not change.

## Recovery and validation

Keep the previous Serving and raw generation. Install through the existing
validated atomic installer only. Before rolling application code back to a
version without v8 support, restore the retained pre-v8 Serving through the
existing rollback procedure. Do not edit pointer JSON by hand.

Tests cover unavailable material, independent field retention, exact inventory,
invalid references, corrupted identity/evidence, legacy v7 rejection, and
same-input idempotency. Real acceptance uses the already downloaded fixed
`20260909T001654097995Z-37354b354360` facts and copied caches, with Provider
calls forbidden and the prior 4/40 ledger unchanged.

The legacy explosion-board API strips the new material-only fields while
preserving its factual response contract; the real HTTP pointer-switch and
fail-closed recovery test covers this boundary. Original Description must match
the validated source fact, not merely carry a valid material-state label.

The real isolated candidate contains 20 factual members: 11 complete material
profiles, 8 partial and 1 unavailable. Repeated build is a no-op, with no new
Provider calls. Runtime installation remains pending: CI reported pre-existing
frontend dependency vulnerabilities (Next.js, sharp, js-yaml and Vitest).
This task does not waive that security gate or include an unreviewed dependency
upgrade. The retained Runtime continues using its previous healthy Serving.
