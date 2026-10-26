# Shared material lifecycle

Scope: reuse the existing Rardar source collectors, immutable evidence, stage
caches, daily checkpoints and consumers. No new scheduler, queue, permission or
budget service. Source collection and saved-stage recovery do not require a
Provider allowance. Normal future generation still uses the shared daily budget.

## Existing capability and the repaired connection

| Existing capability | Observed gap | Minimal change | Regression |
| --- | --- | --- | --- |
| Deterministic project URLs and GitHub metadata | A repository name was treated as identity; verified renames could not continue | Numeric-ID continuity witness and name aliases in the existing metadata cache; bounded same-origin metadata redirects | `test_shared_material_identity.py` |
| Versioned README and content-bound Profiles | Repeated collection could retain old structure indefinitely; unrelated README changes invalidated every model stage | Explicit source refresh, immutable Blob artifacts, stage identities based on their actual inputs | `test_partial_material_reuse.py`, `test_introduction_stage_cache.py` |
| Field isolation and candidate selection | Valid primary reading fields were saved but not independently reusable | Bind existing partial introductions to the existing content/rule/route identity; retain complete-Profile semantics | `test_partial_material_reuse.py` |
| Durable attempts, failure samples and cache-only reassembly | Daily work required budget before recovering already funded stages; repeated semantic failures could repeat across days | Bounded offline recovery before paid work; deterministic next actions from existing receipts; content-bound semantic retry exhaustion | `test_material_lifecycle.py`, `test_material_lifecycle_budgetless_recovery.py` |
| Daily writer lock, work slices and conditional compensation | Partial work and zero-cost waiting could be mistaken for completed or failed work | Keep partial items outstanding; separate cache reuse from new historical admissions; preserve zero-model compensation opportunities | `test_material_recovery_orchestration.py`, `test_daily_refresh_policy.py` |
| Today, historical review, detail and durable Find runs | Name-based reads could split one project; current materials must not rewrite old Find results | Read validated aliases without rewriting original evidence; deduplicate historical work by proven identity | `test_shared_material_consumers.py` |

## Invariants

- Source names, source ranks, observation windows and historical daily batches
  are immutable. Alias resolution does not sum Stars or growth values.
- A 301, similar name or caller-supplied alias is not identity proof. Missing or
  conflicting evidence remains unresolved rather than merging projects.
- Healthy introduction, positioning and capabilities remain independent fields.
  Identity, path, digest and reference violations still reject the affected input.
- Cache-only recovery neither opens a source connection nor calls a Provider.
  A malformed saved artifact is not silently converted into a paid cache miss.
- Stage identities include actual input material, rule/Prompt/Schema versions
  and route identity. Reading an existing result does not make it newly generated.
- Model-generation time is only reported when saved evidence establishes it;
  cache assembly and source-check times are distinct from generation time.
- Same-input semantic failures wait for new input or rules after the existing
  bounded allowance. Transport failures retain their existing cooldown.
- Partial materials remain readable and outstanding. They do not hold back
  ranking publication, and cannot be counted as a complete material result.
- Find runs keep their saved requirements, evidence and result timestamps.
  Current project material is a separate object, not a replacement for old runs.

## Verification boundaries

The automatic new-project and legal-recovery regressions use disposable stores,
synthetic public-source responses and a virtual Provider. Storage and business
policy are real. Cross-process failure replay retains the existing no-network
tests. No development or acceptance Provider request is authorized by this change.

The deployment retains the existing 09:00 main / 11:00 conditional opportunities,
Today growth filter, eight-project historical review and shared daily allowance.
No new timer is introduced. A manual or simulated entry is not evidence that a
future unattended natural cycle has occurred. CI, deployment, content readback,
visual checks and natural operation must be reported separately.
