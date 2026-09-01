# 2026-09-02 Rardar Discover “值得看” Sample Audit

## Research status

This is a real-data, provisional product audit. It is not a production
selection artifact. Gold labels have not been user-confirmed.

Source bindings:

- Observation: `trending-v1-20260901T160000Z`;
- Observation candidates: 500; observations: 499; metadata failures: 1
  (`github_http_404`);
- Today generation: `20260901T001939007155Z-fe663ec7b844`;
- Today exact projects: 480; published Top 20 excluded: 20;
- exact outside Top 20: 459; pre-exact: 2; invalid: 19;
- final eligible universe: 461 numeric GitHub repository IDs;
- canonical profiles already available locally: 21; missing: 440.

The 19 invalid candidates consist of 18 star-count-decrease conflicts from the
audited Today explosion plus the one metadata-incomplete candidate. They were
not silently reintroduced into the sample.

## Sample design

Sixty unique eligible repositories were assigned to five mutually exclusive
research strata, 12 each:

1. high growth / high movement;
2. low momentum but high-value hypothesis;
3. new repository or low-base hypothesis;
4. mature, weak-timeliness hypothesis;
5. negative or noise hypothesis.

The sample covers AI/Agent (21), developer tools (15), data/infrastructure
(12), video/content (6), productivity (5) and other (1). Product forms cover
13 applications, 9 frameworks, 10 SDK/libraries, 5 CLIs, 4 Agent Skills,
5 plugins, 2 API services, 3 datasets/Awesome Lists, 2 knowledge assets,
1 starter and 6 development workflows. These are evidence-derived research
tags, not new Rardar facts.

## Evidence collection

Every sample has one Evidence Package containing identity, GitHub metadata,
Rardar timing/growth facts, README path/blob/excerpts, bounded top-level tree,
release result, canonical-profile fields when present and typed evidence
references. Collection was serial and bounded:

- GitHub calls: 158; no project exceeded 3 calls (limit 4);
- per-call timeout: 8 seconds; response cap: 1.5 MB;
- README evidence: 60/60; README cache hits: 11;
- tree evidence: 60/60; tree cache hits: 11;
- latest release evidence: 39/60; an absent release is explicit, not a failure;
- canonical profile hits: 11/60 sample projects;
- translation cache hits: 9;
- invalid evidence packages: 0;
- cross-repository implementation evidence used as positive proof: 0;
- repository clones, code execution, binaries and issue-history reads: 0.

The FreeDomain README points to a separate source repository. That link is
counter-evidence for this candidate, not permission to borrow the other
repository's implementation.

## Provisional Gold Set

The sanitized [Gold JSON](data/rardar-discover-worth-seeing-gold-v1.json)
contains 24 repositories:

| Label | Count | Interpretation |
|---|---:|---|
| `SELECT_NOW` | 7 | value and deterministic why-now path |
| `WORTHWHILE_NOT_NOW` | 7 | durable value without current trigger |
| `REJECT` | 7 | stable negative reason |
| `UNCERTAIN` | 3 | package cannot support a high-confidence decision |

Positive examples deliberately mix momentum and value: PRAXIST is pre-exact
with a specific research architecture; D2 and workout-guide show low/medium
growth but concrete reusable assets; spaCy is mature but has a release inside
the 14-day window. Negative examples include a high-growth documentation-only
cross-repository surface, an unsafe “unconditional compliance” plugin and a
high-growth duplicate plugin catalog. This prevents stars from defining Gold.

## Model experiment

All probes used TopicEye's existing `routing_group=rardar`, configured
`gpt-5.6-sol` model and JSON/Pydantic boundary. No route, provider, key,
temperature, token limit or reasoning-effort setting changed.

| Metric | Model A: momentum | Model B: value | Model C: value + timeliness | Gate |
|---|---:|---:|---:|---:|
| `SELECT_NOW` precision | 57.14% | 30.43% | 35.00% | ≥80% |
| `SELECT_NOW` recall | 57.14% | 100% | 100% | reported |
| low-growth/high-value recall | 0% | 100% | 100% | ≥70% |
| high-growth/low-value false positives | 66.67% | 100% | 66.67% | ≤20% |
| worthwhile-not-now accuracy | n/a | 0% | 0% | reported |
| primary result evidenceRef validity | n/a | 100% | 100% | 100% |
| eventual primary structured success | n/a | 100% | 100% | ≥95% |

There were exactly 80 top-level invocations: 72 successful structured outputs
and 8 schema-invalid attempts, for 90% per-attempt success. B and C eventually
completed all 24 primary keys under bounded retry. Twelve identical repeat
requests hit the existing control-plane cache and were excluded from
independent consistency. Twelve additional independent provider repeats gave
91.67% decision consistency and 50% Primary Reason consistency. Provider usage
did not expose token counts and the configured route has no pricing fields, so
tokens and cost are unavailable rather than estimated. Mean primary latency was
16.8 seconds for B and 21.1 seconds for C.

No fabricated factual substitutions were found in the reviewed provisional
Gold claims; all successful provider references resolved to their own package.
Model C nevertheless made 13 product classification errors. Most were temporal:
it interpreted a mature repository's first appearance in the six-day Capture
store as “newly observed”, or treated ordinary recent activity as a why-now.
It also selected three semantic negatives because single-candidate evidence did
not supply a deterministic stronger-peer/duplicate decision. These are not
acceptable publication errors.

Model C is therefore the selected *contract shape*, not a ready prompt. The
implementation readiness result is **NO**. Timeliness must be precomputed and
near-duplicate context must be supplied before repeating the evaluation.

## Complete 60-project sample

`Gold` and `Model C` are shown only for the 24 provisional Gold projects. A dash
means the sample was evidence-collected but not labeled or probed as Gold.

| GitHub ID | Repository | Stratum | Today | 24h Δ | Category | Form | Gold | Model C |
|---:|---|---|---:|---:|---|---|---|---|
| 1348577064 | `sapientinc/PRAXIST` | high_momentum | pre-exact | 504 | AI 与 Agent | 框架 | SELECT_NOW | SELECT_NOW |
| 770153867 | `harry0703/MoneyPrinterTurbo` | high_momentum | 21 | 255 | 视频与内容 | 完整应用 | — | — |
| 808144141 | `DigitalPlatDev/FreeDomain` | high_momentum | 22 | 253 | 数据与基础设施 | 知识资产 | REJECT | SELECT_NOW |
| 975734319 | `anomalyco/opencode` | high_momentum | 23 | 251 | AI 与 Agent | 完整应用 | SELECT_NOW | SELECT_NOW |
| 1337955304 | `wang2122/sprix-sage-router` | high_momentum | 24 | 247 | AI 与 Agent | 框架 | — | — |
| 1075372545 | `msitarzewski/agency-agents` | high_momentum | 25 | 241 | AI 与 Agent | 知识资产 | — | — |
| 1042367133 | `github/spec-kit` | high_momentum | 26 | 238 | AI 与 Agent | 开发工作流 | SELECT_NOW | SELECT_NOW |
| 1223170290 | `nexu-io/open-design` | high_momentum | 27 | 234 | AI 与 Agent | 插件 | — | — |
| 1333165619 | `dataelement/dsh-desktop` | high_momentum | 28 | 228 | AI 与 Agent | 完整应用 | — | — |
| 1032808806 | `usestrix/strix` | high_momentum | 29 | 226 | AI 与 Agent | 完整应用 | — | — |
| 1339742577 | `amagine-ai/Amagine3D` | high_momentum | 30 | 220 | 视频与内容 | 完整应用 | UNCERTAIN | SELECT_NOW |
| 21289110 | `vinta/awesome-python` | high_momentum | 31 | 215 | 开发工具 | 数据集 / Awesome List | — | — |
| 6731432 | `koalaman/shellcheck` | low_momentum_high_value_hypothesis | 280 | 5 | 开发工具 | CLI | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 533087958 | `d2lang/d2` | low_momentum_high_value_hypothesis | 283 | 5 | 开发工具 | CLI | SELECT_NOW | SELECT_NOW |
| 83878269 | `treeverse/dvc` | low_momentum_high_value_hypothesis | 327 | 3 | 数据与基础设施 | CLI | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 741524414 | `hey-api/hey-api` | low_momentum_high_value_hypothesis | 275 | 6 | 数据与基础设施 | SDK / Library | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 231972503 | `public-api-lists/public-api-lists` | low_momentum_high_value_hypothesis | 286 | 5 | 数据与基础设施 | 数据集 / Awesome List | — | — |
| 205326947 | `espanso/espanso` | low_momentum_high_value_hypothesis | 328 | 3 | 生产力 | 完整应用 | — | — |
| 828119367 | `yamadashy/repomix` | low_momentum_high_value_hypothesis | 191 | 18 | AI 与 Agent | CLI | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 607289185 | `microsoft/semantic-kernel` | low_momentum_high_value_hypothesis | 426 | 0 | AI 与 Agent | SDK / Library | — | — |
| 458094748 | `omnivore-app/omnivore` | low_momentum_high_value_hypothesis | 429 | 0 | 生产力 | 完整应用 | — | — |
| 7711472 | `zealdocs/zeal` | low_momentum_high_value_hypothesis | 431 | 0 | 生产力 | 完整应用 | — | — |
| 485548415 | `Eventual-Inc/Daft` | low_momentum_high_value_hypothesis | 438 | 0 | 数据与基础设施 | SDK / Library | — | — |
| 257913595 | `voxel51/fiftyone` | low_momentum_high_value_hypothesis | 377 | 1 | 数据与基础设施 | SDK / Library | — | — |
| 1345177309 | `yding-git/personal-edge-proxy` | new_or_low_base | 203 | 15 | 数据与基础设施 | 开发工作流 | — | — |
| 1344425591 | `bryllim/workout-guide` | new_or_low_base | 169 | 22 | 其他 | SDK / Library | SELECT_NOW | SELECT_NOW |
| 1344273611 | `tobi/walgit` | new_or_low_base | 215 | 13 | 数据与基础设施 | 完整应用 | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 1344252356 | `themartiano/try-omarchy` | new_or_low_base | 56 | 121 | 开发工具 | 开发工作流 | — | — |
| 1344223757 | `ShadowAqueduct/watermark-remover` | new_or_low_base | 417 | 1 | 视频与内容 | 插件 | — | — |
| 1343906216 | `fzakaria/selfdb` | new_or_low_base | 250 | 9 | 数据与基础设施 | 开发工作流 | UNCERTAIN | SELECT_NOW |
| 1343146307 | `localai-org/kimodo.cpp` | new_or_low_base | 101 | 59 | 视频与内容 | SDK / Library | — | — |
| 1342943152 | `kgoedecke/doop` | new_or_low_base | 197 | 17 | 生产力 | 完整应用 | — | — |
| 1342930695 | `nateherkai/scroll-craft` | new_or_low_base | 106 | 53 | 视频与内容 | Agent Skill | — | — |
| 1342886503 | `duty1g/x64dbg-mcp-server` | new_or_low_base | 160 | 24 | 开发工具 | 插件 | — | — |
| 1342461518 | `ApodexAI/FrontierAgent` | new_or_low_base | 135 | 32 | AI 与 Agent | 框架 | UNCERTAIN | SELECT_NOW |
| 1342226102 | `kunchenguid/backpass` | new_or_low_base | 217 | 13 | AI 与 Agent | 开发工作流 | — | — |
| 10270250 | `react/react` | mature_low_timeliness | 155 | 24 | 开发工具 | 框架 | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 31792824 | `flutter/flutter` | mature_low_timeliness | 218 | 12 | 开发工具 | 框架 | — | — |
| 2126244 | `twbs/bootstrap` | mature_low_timeliness | 251 | 8 | 开发工具 | 框架 | — | — |
| 70107786 | `vercel/next.js` | mature_low_timeliness | 195 | 17 | 开发工具 | 框架 | — | — |
| 23088740 | `axios/axios` | mature_low_timeliness | 422 | 0 | 开发工具 | SDK / Library | — | — |
| 943149 | `d3/d3` | mature_low_timeliness | 302 | 4 | 数据与基础设施 | SDK / Library | WORTHWHILE_NOT_NOW | SELECT_NOW |
| 90796663 | `puppeteer/puppeteer` | mature_low_timeliness | 304 | 4 | 开发工具 | SDK / Library | — | — |
| 54173593 | `storybookjs/storybook` | mature_low_timeliness | 241 | 9 | 开发工具 | 开发工作流 | — | — |
| 21467110 | `explosion/spaCy` | mature_low_timeliness | 424 | 0 | AI 与 Agent | SDK / Library | SELECT_NOW | SELECT_NOW |
| 45717250 | `tensorflow/tensorflow` | mature_low_timeliness | 164 | 22 | AI 与 Agent | 框架 | — | — |
| 16408992 | `neovim/neovim` | mature_low_timeliness | 199 | 16 | 开发工具 | 完整应用 | — | — |
| 9384267 | `electron/electron` | mature_low_timeliness | 190 | 18 | 开发工具 | 框架 | — | — |
| 1344208527 | `b-nnett/grok-bot-0.18-reconstructed` | negative_or_noise_hypothesis | 225 | 12 | AI 与 Agent | 完整应用 | REJECT | REJECT |
| 1339575436 | `lanicer/cve-2026-41940-PoC` | negative_or_noise_hypothesis | 476 | 0 | 开发工具 | CLI | REJECT | REJECT |
| 1338435811 | `vvxw/deploy-vercel` | negative_or_noise_hypothesis | 216 | 13 | 数据与基础设施 | 模板 / Starter | REJECT | REJECT |
| 1335012977 | `x4gpanell/X4G` | negative_or_noise_hypothesis | 189 | 19 | 数据与基础设施 | API 服务 | — | — |
| 1333000741 | `vibeinging/dsh-desktop` | negative_or_noise_hypothesis | 474 | 0 | AI 与 Agent | 完整应用 | — | — |
| 1335211378 | `Minglink/dsh-infinite-gen-3` | negative_or_noise_hypothesis | 91 | 65 | AI 与 Agent | 插件 | REJECT | REJECT |
| 1334614062 | `apiframe-ai/seedance-2.0-api` | negative_or_noise_hypothesis | 480 | 0 | 视频与内容 | API 服务 | — | — |
| 1337920628 | `MeteorNOX/DeepSeek-Balance-Whale-Widget` | negative_or_noise_hypothesis | 66 | 105 | AI 与 Agent | 插件 | — | — |
| 1336783814 | `flaqai/backlink_skills` | negative_or_noise_hypothesis | 249 | 9 | 生产力 | Agent Skill | REJECT | SELECT_NOW |
| 1144946140 | `mohitagw15856/pm-claude-skills` | negative_or_noise_hypothesis | 340 | 3 | AI 与 Agent | Agent Skill | — | — |
| 1333175049 | `awesome-dsh-plugin/awesome-dsh-plugin` | negative_or_noise_hypothesis | 40 | 181 | AI 与 Agent | 数据集 / Awesome List | REJECT | SELECT_NOW |
| 1201173969 | `JuliusBrussee/caveman` | negative_or_noise_hypothesis | 42 | 172 | AI 与 Agent | Agent Skill | SELECT_NOW | SELECT_NOW |

## Research decision

The evidence supports the product definition and taxonomies. It does not
support implementation readiness. User review is specifically required for the
24 Gold labels, the five Primary Reasons, the strong why-now paths and the
single-stream IA decision.
