# 2026-09-02 Rardar Discover “值得看” Gold Review and Calibration

## Current v3 recovery outcome

The original M3 outcome below is retained as historical evidence. Its Holdout
has since been inspected and is now `historical_revealed_holdout`, not a blind
generalization test. Gate v3 uses a minimal Scope/Value Schema, short Evidence
Aliases, mostly deterministic Timeliness, a bounded meaningful-change
micro-assessment, deterministic Primary Reason and decision, and locally
validated `prompt_json`.

Exactly 9 Gold boundary decisions are now user-reviewed; 27 remain unreviewed.
After label and model freezes, a disjoint 24-project Fresh Holdout ran once and
achieved 24/24 structured/evidence success, 24/24 scope accuracy, 21/24 value
accuracy, 23/24 Timeliness accuracy, 11/12 SELECT precision, 11/14 SELECT recall,
and 5/5 WORTHWHILE accuracy. All frozen gates passed.

- current conclusion: `MODEL_CONTRACT_READY_FOR_FINAL_REVIEW`;
- `READY_FOR_PR26_FINAL_REVIEW = YES`;
- Selection Runtime remains unauthorized until PR #26 final review and merge;
- details: [structured-output recovery](2026-09-02-rardar-discover-structured-output-recovery.md).

## Historical M3 outcome

The research and contract calibration completed, but the model Holdout gates
failed. The correct result is a reviewed provisional Gold v2 and an accepted
M3 architecture with `implementationReady=false`—not a Selection Runtime.

- TopicEye baseline: `dfd9045cc6a647d2832b28ae8bb596ddaa630d39`;
- Rardar baseline: `34556a3ce4765acdc6a91f6fc895846aa33ee5f2`;
- Gold digest: `68445ccf9306db71aeeb360f544deadd7c6bf67fadaca31ecd3b86dcada85d76`;
- model route: existing `routing_group=rardar`;
- model/provider/base URL/reasoning effort: unchanged;
- Production access/writes: 0/0;
- new top-level Provider calls: 90/100; cache hits: 0.

## Gold review and freeze

All 24 original Evidence Packages were reviewed before probing. The 12 added
difficult samples came from the current eligible universe; only three required
bounded new public GitHub evidence. The first freeze exposed a legacy
`counterEvidenceRefs` leakage into the blind Value payload. That run stopped
before item 4, its metrics were discarded, the evidence split was corrected,
and a new Gold digest was frozen. No Gold label changed after the final freeze.

Review actions: keep 22, change 5, needs user decision 9.
All 36 objects record `evidenceReviewed=true`, `calibrationReviewed=true`, and
`userReviewed=false`.

## Model comparison

| Model | Contract | Result |
|---|---|---|
| M0 | one model owns value, timeliness, decision, and reason | 35% SELECT precision; 0% worthwhile accuracy; 66.67% high-momentum false positives; 50% reason repeat consistency |
| M1 | blind Value + model Timeliness + deterministic decision | bounded six-item ablation only; rejected before Holdout because the Provider envelope was unstable |
| M2 | blind Value + deterministic facts; model only eligible for meaningful release/update + deterministic decision | same Holdout semantic decisions as M3; reason still not fixed |
| M3 | M2 + deterministic reason precedence + peer-context-only packing | selected architecture; Holdout gates failed |

M3 is the simplest architecture that enforces every authority boundary. It was
selected for the contract, not approved for implementation.

## Calibration metrics (M3)

| Metric | Result |
|---|---|
| Structured success | 2/18 (11.11%) |
| Evidence validity | 2/2 (100.00%) |
| Fabricated claims | 0/2 (0.00%) |
| SELECT_NOW precision | 1/1 (100.00%) |
| SELECT_NOW recall | 1/6 (16.67%) |
| WORTHWHILE accuracy | 0/6 (0.00%) |
| High-momentum/low-value FP | 0/0 (n/a) |
| Low-momentum/high-value recall | 0/2 (0.00%) |
| Scope accuracy | 2/18 (11.11%) |
| Reason consistency | 18/18 (100.00%) |
| Decision consistency | 18/18 (100.00%) |

The final Calibration run was affected by Provider envelope drift: only 2/18
outputs passed the then-frozen strict envelope. The result is retained as failure
evidence and was not tuned against Holdout.

## Single Internal Holdout metrics (M3)

| Metric | Result |
|---|---|
| Structured success | 11/18 (61.11%) |
| Evidence validity | 11/11 (100.00%) |
| Fabricated claims | 0/11 (0.00%) |
| SELECT_NOW precision | 1/2 (50.00%) |
| SELECT_NOW recall | 1/3 (33.33%) |
| WORTHWHILE accuracy | 6/9 (66.67%) |
| High-momentum/low-value FP | 0/3 (0.00%) |
| Low-momentum/high-value recall | 2/3 (66.67%) |
| Scope accuracy | 8/18 (44.44%) |
| Reason consistency | 18/18 (100.00%) |
| Decision consistency | 18/18 (100.00%) |

## Combined metrics (M3)

| Metric | Result |
|---|---|
| Structured success | 13/36 (36.11%) |
| Evidence validity | 13/13 (100.00%) |
| Fabricated claims | 0/13 (0.00%) |
| SELECT_NOW precision | 2/3 (66.67%) |
| SELECT_NOW recall | 2/9 (22.22%) |
| WORTHWHILE accuracy | 6/15 (40.00%) |
| High-momentum/low-value FP | 0/3 (0.00%) |
| Low-momentum/high-value recall | 2/5 (40.00%) |
| Scope accuracy | 10/36 (27.78%) |
| Reason consistency | 36/36 (100.00%) |
| Decision consistency | 36/36 (100.00%) |

Reason and decision consistency are 100% by deterministic projection of one
validated assessment, not by a new independent Provider repeat. The invalid
initial envelope consumed the safe call budget; no repeat was misreported.

## Holdout threshold gates

| Gate | Result |
|---|---|
| `structuredSuccessGte95` | FAIL |
| `evidenceValidityEq100` | PASS |
| `fabricatedClaimsEq0` | PASS |
| `selectNowPrecisionGte80` | FAIL |
| `selectNowRecallGte70` | FAIL |
| `worthwhileAccuracyGte70` | FAIL |
| `highMomentumLowValueFpLte20` | PASS |
| `lowMomentumHighValueRecallGte70` | FAIL |
| `reasonConsistencyGte80` | PASS |
| `decisionConsistencyGte85` | PASS |
| `scopeAccuracyGte90` | FAIL |

Overall: **FAIL**. Evidence validity, fabricated-claim, high-momentum false
positive, and deterministic consistency gates passed. Structured success,
SELECT precision/recall, worthwhile accuracy, low-momentum recall, and scope
accuracy failed.

## Error matrix

| Set | Repository | State | Expected | M3 | Root cause |
|---|---|---|---|---|---|
| calibration | sapientinc/PRAXIST | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| calibration | github/spec-kit | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| calibration | yamadashy/repomix | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | tobi/walgit | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| calibration | JuliusBrussee/caveman | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| calibration | koalaman/shellcheck | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | treeverse/dvc | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | hey-api/hey-api | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | react/react | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | d3/d3 | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| calibration | DigitalPlatDev/FreeDomain | value_failed | REJECT | UNCERTAIN | schema_invalid |
| calibration | b-nnett/grok-bot-0.18-reconstructed | value_failed | UNCERTAIN | UNCERTAIN | schema_invalid |
| calibration | vvxw/deploy-vercel | value_failed | REJECT | UNCERTAIN | schema_invalid |
| calibration | flaqai/backlink_skills | value_failed | UNCERTAIN | UNCERTAIN | schema_invalid |
| calibration | fzakaria/selfdb | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| calibration | ApodexAI/FrontierAgent | value_failed | UNCERTAIN | UNCERTAIN | schema_invalid |
| holdout | bryllim/workout-guide | completed | UNCERTAIN | SELECT_NOW | scope disagreement |
| holdout | amagine-ai/Amagine3D | value_failed | UNCERTAIN | UNCERTAIN | schema_invalid |
| holdout | lanicer/cve-2026-41940-PoC | completed | UNCERTAIN | REJECT | scope disagreement |
| holdout | massgravel/Microsoft-Activation-Scripts | value_failed | REJECT | UNCERTAIN | schema_invalid |
| holdout | public-api-lists/public-api-lists | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| holdout | voxel51/fiftyone | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| holdout | Eventual-Inc/Daft | value_failed | WORTHWHILE_NOT_NOW | UNCERTAIN | schema_invalid |
| holdout | dataelement/dsh-desktop | value_failed | SELECT_NOW | UNCERTAIN | schema_invalid |
| holdout | vibeinging/dsh-desktop | value_failed | SELECT_NOW | UNCERTAIN | timeout |

## Provider envelope finding

The Provider returned parseable JSON but alternated between enums and
evidence-bearing objects for reasons/assets/aspects, a string or array for
best-fit, and enum or numeric confidence. Known variants were strictly
Pydantic-validated and normalized; unknown fields remained fail-closed. Six
Holdout items still failed schema validation and one timed out. This is a hard
implementation blocker, not a prompt score to hide.

## Proposed Gold changes

| Repository | V1 decision/reason | Proposed v2 decision/reason | Evidence rationale |
|---|---|---|---|
| sapientinc/PRAXIST | SELECT_NOW / distinctive_implementation | SELECT_NOW / directly_reusable | 屏蔽增长后仍有包、示例、测试和评测工作流；V2 确定性优先级将 Primary Reason 改为 directly_reusable。 |
| tobi/walgit | WORTHWHILE_NOT_NOW / distinctive_implementation | SELECT_NOW / directly_reusable | 仓库近期创建且单二进制、对象存储、LFS、UI/API/SDK 已构成完整可用新资产。 |
| JuliusBrussee/caveman | SELECT_NOW / specific_problem_solution | SELECT_NOW / directly_reusable | 可安装 Skill 和固定 benchmark 建立价值；强 momentum 提供独立时效。 |
| d3/d3 | WORTHWHILE_NOT_NOW / distinctive_implementation | WORTHWHILE_NOT_NOW / directly_reusable | D3 的可复用库资产和底层实现都成立；V2 确定性优先级选择 directly_reusable。 |
| b-nnett/grok-bot-0.18-reconstructed | REJECT / — | UNCERTAIN / — | 非官方重构的来源、许可和长期维护边界不足；Scope 也需要产品确认。 |
| flaqai/backlink_skills | REJECT / — | UNCERTAIN / — | 仓库包含可安装 SEO 工作流，但证据尚不足以区分可复用工具与营销渠道。 |
| fzakaria/selfdb | UNCERTAIN / — | SELECT_NOW / directly_reusable | SELF 格式、loader/converter、设计文档与测试证明具体实现；近期创建且交付完整。 |
| d2lang/d2 | SELECT_NOW / directly_reusable | WORTHWHILE_NOT_NOW / directly_reusable | v0.8.2 Evidence Package 没有 release notes，不能把版本号本身视为 meaningful release。 |
| bryllim/workout-guide | SELECT_NOW / directly_reusable | UNCERTAIN / — | 302 项插图和 npm 包价值明确，但面向普通健身内容是否属于 Developer Intelligence 是产品范围决策。 |
| explosion/spaCy | SELECT_NOW / directly_reusable | WORTHWHILE_NOT_NOW / directly_reusable | v3.8.16 是普通 patch，Evidence Package 没有证明新能力或重大行为变化。 |
| awesome-dsh-plugin/awesome-dsh-plugin | REJECT / — | SELECT_NOW / directly_reusable | 可安装插件目录本身具备参考与复用价值；重复只能影响 packing，不能把项目语义改成 REJECT。 |
| lanicer/cve-2026-41940-PoC | REJECT / — | UNCERTAIN / — | 单一认证绕过 PoC 有安全研究价值，但是否属于面向一般构建者的 Discover 需要用户定边界。 |

## User decision packet

Only these nine boundary decisions require user attention:

| Repository | Question | Recommended answer | Alternative | Impact |
|---|---|---|---|---|
| b-nnett/grok-bot-0.18-reconstructed | 非官方重构仓库应一律排除，还是保留为待验证参考？ | 保持 UNCERTAIN，补齐来源和许可证据后再决定。 | 直接 out_of_scope / REJECT。 | 决定非官方逆向工程资产的准入边界。 |
| flaqai/backlink_skills | SEO 外链自动化 Skill 是否属于开发者/产品构建者范围？ | 保持 UNCERTAIN，要求可复用流程和非营销证据。 | 纳入 in_scope，按普通 Skill 评估。 | 决定增长营销工作流是否属于产品能力复用。 |
| fzakaria/selfdb | 实验性系统格式已有代码、设计文档和测试时，是否足以 SELECT_NOW？ | 建议 SELECT_NOW，同时明确实验性质和适用对象。 | 降为 WORTHWHILE_NOT_NOW 或 UNCERTAIN。 | 决定实验成熟度是否阻止新资产推荐。 |
| ApodexAI/FrontierAgent | 关键能力只有 README 声明时，是否保持 UNCERTAIN？ | 保持 UNCERTAIN，要求独立 benchmark 或可复现评测。 | 依据交付树判 strong。 | 决定广泛 AI 能力声明的证据门槛。 |
| bryllim/workout-guide | 面向普通健身内容的结构化插图 SDK 是否属于 Developer Intelligence？ | 保留 scopeStatus=uncertain，用户批准纳入后再改为 in_scope。 | 直接视为 in_scope 并允许其进入 SELECT_NOW。 | 决定 Discover 是否覆盖开发者可复用的垂直内容资产。 |
| awesome-dsh-plugin/awesome-dsh-plugin | 聚合目录有自身价值时，是否允许 semantic SELECT_NOW 但 suppress_duplicate？ | 允许；重复只影响 publicationDisposition。 | 继续把重复目录语义判为 REJECT。 | 决定语义价值和页面去重是否真正解耦。 |
| amagine-ai/Amagine3D | 缺少输出质量样例时，应保持 UNCERTAIN 还是视为强价值？ | 保持 UNCERTAIN，补充真实 CAD 质量证据。 | 按实现树直接判 strong。 | 决定高主张项目所需的外部质量证据门槛。 |
| lanicer/cve-2026-41940-PoC | 单漏洞利用 PoC 是否属于 Rardar Discover？ | 保持 scopeStatus=uncertain；默认不进入普通用户精选流。 | 将防御性安全研究统一纳入 in_scope。 | 决定安全研究与攻击性 PoC 的产品范围。 |
| iptv-org/iptv | 公开 IPTV 链接数据集是否属于 Rardar Discover？ | 保持 scopeStatus=uncertain，先确认版权与开发者价值边界。 | 直接纳入数据集范围。 | 决定带版权争议的公开链接集合是否可精选。 |

## External research artifacts

Stored outside Git at `C:\Users\BRILLI~1\AppData\Local\Temp\rardar-worth-seeing-calibration\20260902T052341Z`:

- `gold-review.json`;
- `gold-freeze-manifest.json`;
- `calibration-results.json`;
- `holdout-results.json`;
- `model-comparison.json`;
- `user-review-packet.json`.

No Provider raw response, complete README, full prompt, secret, or Production
artifact is committed.

## Historical readiness before v3 recovery

- `GOLD-SET = PROVISIONAL_EVIDENCE_REVIEWED`;
- `MODEL-HOLDOUT-GATES = FAIL`;
- `READY_FOR_USER_GOLD_APPROVAL = YES`;
- `READY_FOR_RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01 = NO`;
- `PRODUCTION-DISCOVER = UNCHANGED_DISABLED`.

These values describe the superseded M3 run. Current readiness is recorded at
the top of this document and does not authorize Runtime implementation.
