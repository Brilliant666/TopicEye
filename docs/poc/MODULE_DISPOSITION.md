# TopicEye Module Disposition for Rardar

## 分类规则

- `KEEP`：可直接作为平台底座，语义无需改变；
- `ADAPT`：保留机制，但必须放在 Rardar adapter 或 product profile 后；
- `HIDE`：POC 中不删除，Rardar 产品壳不展示；
- `DEFER`：可能有价值，但当前没有足够证据进入第一阶段；
- `REMOVE_LATER`：只有正式迁移、上游同步和回滚评估完成后才可删除。

## 处置矩阵

| TopicEye 模块 | 分类 | POC 证据 | 正式边界 |
| --- | --- | --- | --- |
| FastAPI app / middleware / health | KEEP | secure fork base 使用 FastAPI 0.133.0 / Starlette 1.3.1，real HTTP 通过 | 保留请求 ID、限流、错误边界 |
| SQLAlchemy async + repositories | KEEP | 两张真实 PG 表 | Rardar repository 按分层新增 |
| Alembic startup migration | KEEP | PostgreSQL 16.15 upgrade head | 不手写运行时 DDL |
| durable Job pattern / lease | ADAPT | Find Project quick/deep/retry | 扩展为正式 AIJob contract |
| LLM model routing | ADAPT | medium/high/xhigh 已穿透 | provider 必须经 capability probe |
| response cache | ADAPT | cache hit 有审计 | cache key 必须含 evidence/prompt/schema version |
| failover / cooldown | ADAPT | 429/5xx 行为可观测 | 单模型第一版不能伪装为多模型高可用 |
| circuit breaker | KEEP | open/recovery 已验证 | 与事实发布隔离 |
| LLM usage log | ADAPT | token/latency/attempt 可记录 | 禁止 Key 和敏感 payload |
| TopicEye admin shell | KEEP | `/admin` 未换壳 | 增加 Rardar diagnostics 页面 |
| TopicEye auth / roles | DEFER | admin 壳继续受保护 | 产品用户模型另行设计 |
| scheduler skeleton | DEFER | 本 POC 显式关闭 | 不能取代 Rardar observer/scheduler |
| ContentItem / content ingestion | HIDE | 未参与三条切片 | 不承载 GitHub repository facts |
| RSS / webnovel / creator modules | HIDE | Rardar nav 不暴露 | 不删除，保持 default TopicEye |
| TopicEye scoring / trending rank | HIDE | 没有改变爆发榜名次 | 不得影响 observedStarDelta |
| daily/weekly/monthly digest | HIDE | POC 未使用 | 后续按产品证据决定是否适配 |
| favorites / reading / creation | HIDE | POC 未使用 | 不能自动映射为 Rardar Action |
| notification infrastructure | DEFER | 未做产品验证 | 未来 Job 完成提醒可评估 |
| DuckDB analytics | DEFER | 产品启动时关闭；完整回归用官方 `postgres_scanner` artifact 验证真实 PG ATTACH | 长期趋势规模验证后再决定 |
| existing TopicEye product routes | HIDE | default=false build/test 保留 | product mode 下由壳隐藏 |
| upstream legacy modules | REMOVE_LATER | 本 POC 没有删除 | 需独立 PR、使用数据与回滚证据 |
| Python dependency security baseline | KEEP | PR #2 已合入，cryptography 50.0.0，pip-audit 0，main security-scan PASS | 持续跟踪 advisory；不得用 ignore/allowlist 降低门禁 |

## Repository 不是 Content

本 POC 明确选择 `NO`：Rardar GitHub repository 不映射为 TopicEye `ContentItem`。原因：

1. repository 是持续演化实体，不是一次性内容条目；
2. Star observation、release、static evidence 和 AI profile 有独立版本；
3. Content score 会诱导事实榜被 TopicEye 产品语义污染；
4. stable project identity 和 generation rollback 已在 Rardar 中有合同；
5. 未来可以复用 TopicEye 的基础设施，不需要复用错误的数据模型。

## 本 POC 的适配面

核心适配被限制在：

- central ProductProfile；
- strict `RardarIntelligenceAdapter`；
- 两张 POC control-plane 表和一个 migration；
- 一个 Rardar API router、service 和独立 Worker；
- Mock provider hook，仍走原 LLM chain；
- 非 admin Rardar product shell；
- 版本化 fixture 与测试。

为让 pinned upstream 在 Windows 完整回归可执行，另有小型平台兼容修正：DuckDB extension 名、高精度缓存/限流时钟、Windows RSS 采集，以及不依赖数据库连接失败的任务生命周期测试。

没有修改 TopicEye Content、scoring、scheduler、auth、admin permission 或现有业务表。

## 上游同步原则

正式融合必须保留 `upstream` remote，定期在独立分支上 rebase pinned upstream，并执行：

1. default TopicEye full test/build；
2. Rardar product mode full test/build；
3. migration upgrade/downgrade review；
4. adapter boundary diff；
5. LICENSE/NOTICE 与依赖审计；
6. 资源回归和真实 HTTP 测试。

任何 `REMOVE_LATER` 都不得和首次平台融合放在同一 PR。
