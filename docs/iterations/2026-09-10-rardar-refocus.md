# RARDAR-REFOCUS-01

Scope: TopicEye product implementation from `bdb3c01`; reviewable branch only.
No main merge, Runtime replacement, cloud operation, new budget, or model call.

## Product changes

- Today: direct public GitHub daily + Trendshift own daily union, interleaved
  source order, source-specific ranks/dates/metrics, complete list and stable-ID
  details independent of Explosion/observation/Profile completeness.
- Historical Hot: distinct lifetime-appearance evidence plus retained daily
  snapshots; existing validated readings and bounded shared Profile processing.
- Rardar News/Discover executable entries paused; old links explain the pause.
  Candidate/watchlist product entries retired; internal records remain intact.
- Find/shared materials/daily budget and interactive priority remain. The next
  Find work stays demand-led; Activity content is undecided; TrendRadar is an
  independent future integration, not installed here.

## Real source evidence (not fixtures)

Captured 2026-09-10 13:34:44 UTC: GitHub daily 16, Trendshift own daily 25,
intersection 8, union 33. GitHub exposes daily semantics without an absolute
date; Trendshift public data exposes 2026-09-10. The public historical GitHub
Trending appearance index supplies 25 projects with lifetime counts but no
individual appearance dates. Historical union: 57, four existing readable
interpretations (including Microsoft MarkItDown); no new AI output generated.

The public pages, not the paid Signal API, are read. Public HTML can change;
parser errors retain valid prior data. No raw captures or private local data
are committed. Latest live captures can differ from these measured counts.

## Evidence boundaries

Focused storage/scope/daily/collector tests cover zero-budget collection,
failure isolation, all-source preservation, complete union, path/integrity
checks, history counts, cache reuse, durable attempts and retired entry guards.
Production browser tests use labelled synthetic responses, desktop and mobile,
including Find, administrator authorization and retired routes.

The isolated real-data API served all 33 matching project details and 57
historical projects. Local production frontend creation was rejected by the
execution policy; it was not retried via alternative wrappers. Therefore the
real-data local browser preview is not claimed complete. The pre-existing
Runtime's 3000/8102 health checks were unavailable before changes; it was not
restarted or replaced. Existing daily budget was 100/100, new calls zero.
New historical model generation and natural-day unattended execution are not
verified by cache replay or a manually exercised scheduler function.

## September 11 acceptance continuation

The original PostgreSQL 16 instance was restored with its existing 16.15
binary, without initialization or migrations. One real historical reading for
`codecrafters-io/build-your-own-x` was generated through `historical_work` and
the original daily budget identity: one request, then an individual cache hit
with model generation disabled. The saved reading was observed through the
real API and mobile detail page. These results supersede the earlier zero-call
and database-unavailable observations; they do not prove unattended scheduling.

The manually started production frontend displayed the full 33-project real
snapshot after Load more. Normal login and authenticated configuration checks
remain pending until the managed preview is connected to the original database.

### Execution-layer diagnosis

Observed desktop package: `26.903.9818.0`; bundled CLI: `0.153.4`.
The active session reports `danger-full-access` and approval policy `never`.
The user rules file contains allow rules only; a read-only `execpolicy check`
found no matching rule for the preview command. No project-local rule file was
present. Rejection messages say `CreateProcess ... rejected: blocked by policy`
before shell creation, so these attempts are not application startup failures.
The bounded local log query found session-level rejection records, not a named
deny rule or an approval request. The exact internal policy decision is therefore
unresolved, not attributed to PowerShell ExecutionPolicy, filesystem access,
or a proven client defect. No global settings/rules were changed.

The project local-environment Actions invoke the same `rardar-local.ps1`
preview entry used by the operator/agent, not alternate launch implementations.
They are ordinary UI actions, not a policy bypass. Their existence alone does
not establish that automated process creation is permitted or that acceptance
has completed.
### 2026-09-11 固定预览入口实测

- 同一 `scripts/rardar-local.ps1` 现提供 `preview-build/start/status/restart/stop`；Codex local environment Actions 调用相同入口。普通启动不安装、不构建、不启动数据库或调度。
- 独立 `.next-preview` 和 54190/54191 已由执行工具实际启动；重复 start 复用健康进程，restart 定向替换本预览，原 PostgreSQL PID 保持不变。当前环境不再需要人工维持前后端终端。
- 配置/状态/日志保存在本机 `%LOCALAPPDATA%/TopicEye/rardar-previews/<worktree-hash>`；预览资料隔离，预算绑定原 Runtime 身份。只读正式预算查询为 2026-09-11 Asia/Shanghai 1/100、交互预留10，本轮启动验收新增请求0。
- 真实 Playwright 浏览器通过实际54190应用和54191后端，在1440及390宽度读取33项完整去重列表、57项历史列表与 codecrafters 已保存新解读；暂停模块显示明确说明，无页面异常或横向溢出。没有拦截或替换API响应。
- Codex浏览器控制连接仍返回 `nodeRepl.fetch request failed`；这与正常启动入口成功是不同结果。登录页面和Find表单可读，但登录后的管理操作与Find实际需求提交尚未完成，PR继续Draft。
- 先前 `blocked by policy` 已确认属于shell创建前拒绝；当前用户allow规则没有提供对应拒绝解释，无法从已有记录确定隐藏策略的具体判定。未修改规则、权限或安全配置。
### 2026-09-11 REFOCUS-03 正式入口与切换准备

- 正式 `start/status/restart/stop/build` 与 Preview 共用进程身份、构建绑定、预检与健康检查；仅原 Runtime 配置记录的目录可启动3000/8102。正式模式使用原资料与预算身份、正常lifespan和既有scheduler，不再以Selection或SSH同步为启动前置。
- 普通start不安装或构建；显式build绑定8102且拒绝覆盖正在服务的构建。自动迁移、seed和sequence修复关闭，原PostgreSQL必须已健康。停止仅移除进程状态，持久配置继续支持再次启动。
- Actions明确区分“Run Rardar (3000)”与Preview，均调用同一脚本实现；正式动作指向原运行目录，不从开发worktree长期提供正式服务。
- 修正focused CI测试的跨平台假路径：Ubuntu不存在C盘，测试改用tmp_path；生产进程身份检查未放宽。
- 已以原测试账号完成真实预览登录和管理员预算读取（HTTP200）；Find真实需求经3条GitHub查询提交并返回，新增2次统一计量请求。没有改密码或模型配置。
- 原数据库pg_dump备份已完成并验证归档目录；预览资料在仓库外候选目录经原校验/发布函数验证33项Today、57项历史和codecrafters解读。正式数据带回、合并及3000验收结果在PR收口记录中另行确认，不能将准备状态当作部署完成。

### 2026-09-11 TODAY-HISTORY-RESTORE-01 产品回归修复

以已合并的 `1c48925` 为基线，保留双榜来源、统一预算和固定启动入口，恢复原版 Today 的完整卡片、详情、资料与按需解读能力；历史入口前台统一为“历史回顾”，与今日热榜共用展示和项目资料。Find 保留，动态仅占位，News/Discover/候选池/观察列表仍暂停。

| 原能力 | 已复现缺口 | 修复位置 |
| --- | --- | --- |
| 完整官方档案、能力标题/来源、判断、差异与使用入口 | `project_material` 只输出简化字符串并固定清空限制，新 stable 路由未使用完整详情组件 | 共用材料映射、原详情组件的榜单上下文适配 |
| 同项目跨入口复用有效资料 | 历史页实时读取材料，Today 固定在生成快照时的简化材料 | 身份/证据验证后的共用材料读取 |
| 按需单项目解读与结果复用 | 新路由缺入口，旧调用要求 Explosion/Discover 成员 | 现有分析引擎的稳定项目身份适配 |
| 真实同步状态 | 旧 Exact 24h 操作被默认当成双榜状态 | 操作上下文区分，原记录不改写 |

真实基线保留：`tt-a1i/archify` 的 2026-09-10 有效 Serving 档案含4条能力、2项差异、9个使用入口和 Rardar 判断；原 numeric 路由在桌面/手机可读。该份档案与8月截图资料版本不同，未从截图补造字段。前后对照与正式验收记录在本修复PR中持续补充，未通过部分不记作完成。
