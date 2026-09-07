# 2026-09-07 — Rardar Discover core-flow simplification

## Goal and boundary

Task `RARDAR-DISCOVER-CORE-FLOW-SIMPLIFICATION-01` fixes three coupled defects
without adding another evaluator or score: alphabetic recall occupancy,
keyword-shaped Value evidence loss, and Timeliness-gated publication. Today,
Find Project, Rardar facts, databases, Production and the daily Runtime are not
changed. Real application Provider calls are zero.

## Runtime contract

- Recall keeps the existing universe, Today Top 20 exclusion, six channels and
  momentum-only cap. A validated `recallBatchId` drives a SHA-256 order over
  policy, batch, channel and numeric repository ID. The build and Shadow freeze
  record the batch; GET requests do not select or advance it.
- Evidence Alias v2 removes only explicit popularity facts or affected
  sentences. It preserves legitimate functional descriptions containing
  `window`, `delta`, `growth`, `recent`, `新增`, `增长`, `Star` or `fork`, and
  records `projectionRule` beside source path and revision.
- Publication Policy v1 requires a complete same-repository
  `in_scope`/`strong`/`high` Value Gate with a supported Primary Reason. The
  retained `semanticDecision` remains readable but is not a new-publication
  gate. Timeliness is optional, cannot change membership or order, and the
  ordinary main/Shadow path makes no Meaningful Change call.
- Candidate observation histories shorter than 26 hours remain eligible for
  Value evaluation; `observedStarDelta` is `null` until the complete window is
  available. Today's exact 24-hour contract is unchanged.
- Packing retains stable duplicate suppression and a maximum of six. It adds
  no Discovery Fit layer, score, reason-count ranking or named-project rule.

## Frozen 16-item rule replay

The immutable artifact
`shadow-4bd62ed435c4ca2e32e410a346610581` was parsed and audited under its
original Evidence Alias v1 digest. Its original Gate inputs and results were
not rebound to v2 evidence.

| Result | Count | Repositories |
|---|---:|---|
| Old publish (`SELECT_NOW`) | 3 | `200ok-ch/organice`, `appsmithorg/appsmith`, `agno-agi/agno` |
| New Value-eligible | 9 | the old 3 plus `agent-sh/agentsys`, `angular/angular`, `ant-design/ant-design`, `Avaiga/taipy`, `basicmachines-co/basic-memory`, `AmintaCCCP/GithubStarsManager` |
| Published within capacity | 6 | `AmintaCCCP/GithubStarsManager`, `agno-agi/agno`, `agent-sh/agentsys`, `appsmithorg/appsmith`, `200ok-ch/organice`, `angular/angular` |
| Capacity-suppressed | 3 | `ant-design/ant-design`, `Avaiga/taipy`, `basicmachines-co/basic-memory` |
| Still ineligible | 7 | five moderate/medium Value cases, one medium-confidence strong case, and one interrupted Gate |

This is a publication-rule replay, not a new quality evaluation. It proves the
six Timeliness-only holds no longer veto valid Value; it does not prove that a
fresh v2 Gate would return the same result.

| Repository | Original result | New rule outcome | Reason |
|---|---|---|---|
| `agno-agi/agno` | `SELECT_NOW` / publish | publish | complete strong/high Value |
| `agent-sh/agentsys` | `WORTHWHILE_NOT_NOW` / hold | publish | complete strong/high Value; prior hold was Timeliness-only |
| `angular/angular` | `WORTHWHILE_NOT_NOW` / hold | publish | complete strong/high Value; prior hold was Timeliness-only |
| `appsmithorg/appsmith` | `SELECT_NOW` / publish | publish | complete strong/high Value |
| `andresgongora/synth-shell` | `UNCERTAIN` | ineligible | Gate was interrupted; no valid Value result |
| `200ok-ch/organice` | `SELECT_NOW` / publish | publish | complete strong/high Value |
| `521xueweihan/HelloGitHub` | `UNCERTAIN` | ineligible | Value was moderate |
| `air-embodied-brain/Zetta-Embodiment` | `UNCERTAIN` | ineligible | strong Value had only medium confidence |
| `avelino/awesome-go` | `UNCERTAIN` | ineligible | Value was moderate |
| `awesome-dsh-plugin/awesome-dsh-plugin` | `UNCERTAIN` | ineligible | Value was moderate |
| `apiframe-ai/seedance-2.0-api` | `UNCERTAIN` | ineligible | Value was moderate with medium confidence |
| `ant-design/ant-design` | `WORTHWHILE_NOT_NOW` / hold | capacity-suppressed | Value-eligible; six-item capacity reached |
| `Avaiga/taipy` | `WORTHWHILE_NOT_NOW` / hold | capacity-suppressed | Value-eligible; six-item capacity reached |
| `basicmachines-co/basic-memory` | `WORTHWHILE_NOT_NOW` / hold | capacity-suppressed | Value-eligible; six-item capacity reached |
| `AmintaCCCP/GithubStarsManager` | `WORTHWHILE_NOT_NOW` / hold | publish | complete strong/high Value; prior hold was Timeliness-only |
| `alvinreal/awesome-opensource-ai` | `UNCERTAIN` | ineligible | Value was moderate with medium confidence |

## Recall and evidence replay

On the frozen 478-project universe, the old first 48 began with alphabetically
early repositories. The default v2 batch
`source-b9a1391d86788b518311aadd` selected 48 with only 9 overlapping the old
set. Across that batch plus eight explicit offline batches, cumulative unique
coverage was `48, 90, 125, 158, 187, 212, 232, 247, 261`. This demonstrates
rotating TopicEye recall opportunity, not removal of all upstream source bias.

The default batch started with `Significant-Gravitas/AutoGPT`,
`syv-ai/qwen38-27b-rtx3090`, `missuo/herdrm`, `0xPlaygrounds/rig`,
`jeremy-prt/bloub`, `amicalhq/amical`, `refinedev/refine`, `ruvnet/RuView`,
`YangJiiii/3105` and `ViscousPot/GitSync`. Only 7/48 had a current healthy
Profile in the frozen cache; the build does not fall back to the old
alphabetical set. All new or materially reprojected inputs require their own
future assessment.

<details>
<summary>Default v2 recall batch (48 candidates)</summary>

1. `Significant-Gravitas/AutoGPT` (`614765452`)
2. `syv-ai/qwen38-27b-rtx3090` (`1334946608`)
3. `missuo/herdrm` (`1339208118`)
4. `0xPlaygrounds/rig` (`810861466`)
5. `jeremy-prt/bloub` (`1335104760`)
6. `amicalhq/amical` (`980286881`)
7. `refinedev/refine` (`331293626`)
8. `ruvnet/RuView` (`997737944`)
9. `YangJiiii/3105` (`1333728741`)
10. `ViscousPot/GitSync` (`812362660`)
11. `awesome-dsh-plugin/awesome-dsh-plugin` (`1333175049`)
12. `rtk-ai/rtk` (`1139971460`)
13. `iluwatar/java-design-patterns` (`22790488`)
14. `Anionex/dsh-vision-toolkit` (`1333100071`)
15. `alchaincyf/deepseek-harness-orange-book` (`1333742677`)
16. `mateodelnorte/meta` (`76408906`)
17. `public-api-lists/public-api-lists` (`231972503`)
18. `Zyrexnn/Cybermes` (`1339614046`)
19. `mono0926/LicensePlist` (`89676988`)
20. `Snailclimb/JavaGuide` (`132464395`)
21. `xiaobright/dsh-anchored-standard` (`1334245678`)
22. `GoogleContainerTools/skaffold` (`118654121`)
23. `sickn33/agentic-awesome-skills` (`1134426800`)
24. `kserve/kserve` (`178075572`)
25. `ant-design/ant-design` (`34526884`)
26. `deeplearning4j/deeplearning4j` (`14734876`)
27. `davatron5000/microlighter` (`1333304994`)
28. `liyupi/ai-guide` (`931950959`)
29. `lissy93/dashy` (`343078060`)
30. `ruanyf/weekly` (`152870372`)
31. `dsh-tauri-desk/deepseek-harness-desktop` (`1333718792`)
32. `thedotmack/claude-mem` (`1048065319`)
33. `apiframe-ai/seedance-2.0-api` (`1334614062`)
34. `avelino/awesome-go` (`21540759`)
35. `ossu/computer-science` (`19415064`)
36. `wang2122/sprix-sage-router` (`1337955304`)
37. `FlorianBruniaux/claude-code-ultimate-guide` (`1131107802`)
38. `unhappychoice/gittype` (`1046385861`)
39. `ZSvirt/zsvirt` (`1333884889`)
40. `kornia/kornia` (`145693916`)
41. `Electricitysheep/dsh-handbook` (`1333258936`)
42. `esengine/DeepSeek-Reasonix` (`1216785679`)
43. `ankitpokhrel/jira-cli` (`314995099`)
44. `decionis/agent-safe-pipeline` (`1333556422`)
45. `ccch1mneyyy/dsh-TUI` (`1333111893`)
46. `carla-simulator/carla` (`108102826`)
47. `Shubhamsaboo/awesome-llm-apps` (`793375104`)
48. `FuJacob/cotabby` (`1201537262`)

</details>

On the 41 healthy profiles from the former recall, v2 restored legitimate
evidence in six repositories. Examples include ActivityWatch's window watcher
and `aw-watcher-window` path, GithubStarsManager's Star-collection function,
agent-deck's session-fork workflow, and a `business-growth` directory. Explicit
Star totals, growth/rank facts and popularity endorsements remain excluded.

## Compatibility and verification

Evidence Alias v1 is projected back to its exact historical digest shape for
retained Shadow artifacts and Meaningful Change contexts. New v2 fields are
strictly validated and digest-bound; atomic publication and fail-closed Value
behavior are unchanged. Historical research metrics remain historical and are
not relabelled as if this policy had existed then.

The implementation is complete only after focused backend tests, the relevant
backend/frontend suites, production build, security checks, exact-head CI and
an isolated production-component browser check. Production activation and real
model reevaluation remain separate work.
