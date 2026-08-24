# Rardar × TopicEye 平台融合纵向 POC

## 结论摘要

本 POC 最初在固定的 TopicEye 上游提交 `8b559895c6e3547550a85ac561cfee4a42113448` 上完成三条可运行纵向切片；现已 rebase 到 fork 的安全 main `f1c80188de7f05ba4285de48f962b7b31656d930`（PR #2）。三条切片仍是今日爆发榜、Mock Sub2API 分析链和 Find Project durable Job。结果支持 `GO_PLATFORM_FUSION`：TopicEye 可以作为 Rardar 的控制面、异步执行与管理基础，但不能成为 GitHub 事实、artifact 或 generation 的权威来源。

正式产品边界是：

> TopicEye inside, Rardar outside.

- Rardar 保持产品名、信息架构、亮色蓝白视觉和事实语义。
- TopicEye 提供 FastAPI、PostgreSQL、Job、LLM 控制链、管理后台与运维骨架。
- 双方通过严格 adapter 相接；Rardar artifact 继续 fail closed。
- 本分支是 POC，不是迁移分支，不能部署、Ready 或合并。

## 不可变基线

| 项目 | 固定值 |
| --- | --- |
| Rardar read-only baseline | `e21c5e258c63140ff941434e0f57514893258b42` |
| TopicEye upstream | `fxbin/TopicEye` |
| TopicEye original upstream provenance | `8b559895c6e3547550a85ac561cfee4a42113448` |
| TopicEye current secure fork base | `f1c80188de7f05ba4285de48f962b7b31656d930`（PR #2） |
| 合法 fork | `Brilliant666/TopicEye` |
| POC 分支 | `poc/rardar-product-shell` |
| License | Apache-2.0，根目录 `LICENSE` 原样保留 |
| Rardar 仓库 | 全程只读、未切分支、未写入 |
| Production | 未访问 |

## Python 安全基线

```text
POC_SECURITY_BASELINE = RESOLVED
```

PR #2 已独立合入 FastAPI `0.133.0`、Starlette `1.3.1` 和 cryptography `50.0.0`；Pydantic 维持 `2.10.4`。安全 main 的 workflow-dispatch CI 五项全绿，`pip-audit = 0`，没有通过 ignore、allowlist 或降低 CI 门禁绕过 finding。原 POC 的 `security-scan` 红灯来自旧 upstream 依赖，rebase 后不再是平台融合阻塞项。

该结论不消除其他产品化风险：约 930.7 MB 实测总 RSS、长期 fork 维护成本、真实 Sub2API capability/security probe、正式 observer/scheduler、Production 备份与回滚均仍待独立验证。本分支继续是 evidence-only Draft，不是 Production 或 merge 候选。

## 范围与非目标

本 POC 只回答“TopicEye 是否适合成为 Rardar 平台底座”。它不做真实数据迁移，不使用真实 Sub2API Key，不调用 `api.cosflow.icu`，不发布公开站点，也不把 Rardar repository 强行塞入 TopicEye `ContentItem`。

明确未实现：

- 真实 GitHub observer、production generation 或 D1 迁移；
- 真实 Sub2API capability probe；
- 动态 GitHub Search、Trendshift 或私有仓库 GitHub App；
- 完整候选池、观察列表、资产库和生产权限模型；
- 上游 TopicEye 模块删除或正式产品迁移。

## 真实运行环境

Docker Desktop 4.22 的本机 daemon 因 `rpcbind terminated unexpectedly` 无法稳定提供容器能力。POC 没有以 SQLite 替代，而是从 EnterpriseDB 官方 PostgreSQL Windows binary archive 启动 PostgreSQL 16.15：

- 绑定：`127.0.0.1:55432`；
- 数据库：`topiceye_poc`；
- 数据与二进制：仓库外 `AppData\\Local\\TopicEyeRardarPoc`；
- 下载包 SHA-256：`25E6FCDFB8CAEC38691BF461125E7564508760666F7B8E5DC6A5F0818F58F81E`；
- migration head：`4d8a71c9f201`；
- POC 表：`rardar_find_project_jobs`、`rardar_ai_requests`。

这满足“真实 PostgreSQL”门禁，同时把 Docker 故障明确记录为平台运维风险，而不是静默降级。

## Slice A：Audited Explosion Board

`RardarIntelligenceAdapter` 只读取版本化 fixture pointer 和 revision：

1. 拒绝 symlink、路径逃逸和非法 pointer；
2. 校验 pointer Schema、artifact SHA-256 和 artifact Schema；
3. 每个请求只加载一次 pointer/一个 artifact revision；
4. 精确 Top 5 按 `observedStarDelta DESC, totalStars DESC, repository ASC`；
5. PostgreSQL 和 TopicEye score 都不能重排事实榜；
6. 原子切换 pointer 后，新请求读新 revision，单个响应不混代；
7. AI 失败时 HTTP 仍为 200，事实、名次、来源和待验证区仍可见。

POC fixture 包含精确 Top 5 和“新入榜待验证”3 个项目。所有项目和证据均为明确标注的测试 fixture，不声称代表当日真实 GitHub 全站榜单。精确项目携带 `projectId`、GitHub numeric ID、24h 窗口、能力和来源；待验证项目使用独立的 `observedWindowStarDelta`，不会把短窗口增长冒充精确 24h delta。

## Slice B：Mock Sub2API through TopicEye

确定性 Mock provider 没有网络代码，固定记录：provider、base URL identifier、`gpt-5.6-sol`、reasoning effort、scene、request ID、input hash、延迟、token usage、attempt 和结果状态。

调用没有绕过 TopicEye：它经过模型配置、routing group、并发/速率边界、response cache、failover、usage log 和 circuit breaker，再由 Rardar 执行本地 JSON/Schema 验证。行为测试覆盖：

- medium、high、xhigh 三档 effort；
- 同一输入跨 effort 不共用缓存，重复同档调用才可命中；
- success、timeout、429、5xx；
- invalid JSON、Schema mismatch；
- cache hit；
- circuit open、half-open recovery；
- AI failure 不改变 explosion board 的事实排名。

该结果证明了平台能力，不代表真实 Sub2API 已兼容；真实 provider 仍必须通过独立 capability probe。

## Slice C：Find Project durable flow

自然语言需求和可选公开 GitHub URL 被持久化为 PostgreSQL Job。独立 Worker 使用租约和 `FOR UPDATE SKIP LOCKED` 领取任务，状态为：

```text
queued
→ parsing_requirement
→ quick_candidates_ready
→ deep_analysis
→ ready | failed
```

high 负责生成可编辑 RequirementProfile；用户确认后，xhigh 在同一次调用中比较最多 5 个版本化候选，最终输出恰好 3 个带工程证据、许可证风险、复用类型、集成工作项和下一验证动作的结果。

RequirementProfile 完整包含 goal、must-have、nice-to-have、constraints、exclude、technology stack、deployment、license preference、reuse granularity 与 acceptance criteria。模式 B 额外保留公开 GitHub repository URL 上下文。最终页面不只展示推荐摘要，也展示 must-have 覆盖、缺失/未知能力、技术兼容、reference kinds、证据引用和许可证风险。

已验证：

- 页面刷新后 Job 和结果仍存在；
- 首次 Worker 失败可以从持久 retry state 恢复；
- 删除 Job 不删除 artifact；
- pointer 切换不会回写历史 Job 的来源 revision；
- PostgreSQL 只拥有控制面状态，不拥有榜单事实。

## 运行方式（仅隔离 POC）

以下值只是示例。不得使用 3000/3002，不得填入真实 AI Key：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://topiceye@127.0.0.1:55432/topiceye_poc"
$env:RARDAR_PRODUCT_MODE = "true"
$env:SCHEDULER_ENABLED = "false"
$env:CACHE_WARMUP_ENABLED = "false"
$env:DUCKDB_STARTUP_INIT_ENABLED = "false"

# backend，随机回环端口
python -m uvicorn app.main:app --host 127.0.0.1 --port 61981

# 独立 Worker
python -m app.rardar.worker

# frontend，另一个随机回环端口
$env:BACKEND_API_URL = "http://127.0.0.1:61981"
npm run dev -- --hostname 127.0.0.1 --port 61982
```

`RARDAR_PRODUCT_MODE=false` 是默认值；默认 TopicEye backend、frontend build、旧路由和原测试必须继续通过。本 POC 的 scheduler、cache warmup、startup seed 与 DuckDB startup 开关仍由启动环境显式关闭；`RARDAR_PRODUCT_MODE` 本身不会偷偷改写这些既有运维开关。正式融合需要把这组值固化为可审计 runtime profile。

Windows 完整回归还暴露并验证了三项上游可移植性修正：DuckDB 1.2.2 的官方扩展 artifact 名为 `postgres_scanner`（`ATTACH TYPE postgres` 不变）、缓存/限流使用高精度 `perf_counter`、进程指标使用 Windows `GetProcessMemoryInfo`。这些修改保持默认产品语义，但会增加后续 upstream rebase 审查面。

## 量化结果

最终测量使用 production frontend、warm backend、独立 Worker 和同一 PostgreSQL 实例。具体数值在最终验证完成后锁定于本表：

| 指标 | 结果 |
| --- | ---: |
| TopicEye baseline files | 717 |
| POC changed files | 70 |
| 既有核心文件修改 | 15 |
| 新增 PostgreSQL tables / migrations | 2 / 1 |
| 新增 API endpoints | 9 |
| 新增 Rardar UI routes | 7 |
| 后端 / 前端 / E2E 新测试 | 11 / 2 / 8 次浏览器项目执行（7 PASS、1 有意 skip） |
| Frontend RSS | 103.6 MB |
| Backend RSS | 364.2 MB |
| Worker RSS | 290.5 MB |
| PostgreSQL RSS | 172.4 MB |
| 合计 RSS | 930.7 MB |
| cold / warm homepage | 253.4 ms 首次 HTTP / 25.6 ms 五次 warm 平均；Next ready 147 ms |
| production build | 10.01 s（Rardar mode）；10.20 s（default mode 回归） |
| 仓库磁盘增量（不含 node_modules/.venv） | 1.19 MB net（其中截图 1.01 MB） |

## 证据索引

- [架构边界](./ARCHITECTURE.md)
- [UI 迁移验证](./UI_MIGRATION.md)
- [模块处置](./MODULE_DISPOSITION.md)
- [GO/NO-GO](./GO_NO_GO.md)
- [第三方归属](./THIRD_PARTY_ATTRIBUTION.md)
- [桌面爆发榜](./screenshots/explosion-board-1440x900.png)
- [手机找项目完成态](./screenshots/find-project-ready-375x812.png)
