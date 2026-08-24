# POC Architecture

## 架构判断

TopicEye 适合作为 Rardar 的平台控制面，而不是事实数据库。融合后的最小可靠边界如下：

```text
Versioned Rardar artifact / pointer
        │ strict read + hash + Schema
        ▼
RardarIntelligenceAdapter ───────────────┐
        │ one request / one revision     │
        ▼                                │
Rardar product API + product shell      │ factual authority
        │                                │ stays outside PostgreSQL
        ├───────────────┐                │
        ▼               ▼                │
PostgreSQL Job      TopicEye LLM chain   │
control state       + Mock Sub2API       │
        │               │                │
        └──── independent Worker ─────────┘
```

## 中央 ProductProfile

产品差异只有一个入口：backend `RARDAR_PRODUCT_MODE` 和 frontend 由 Next config 编译注入的同名 profile。所有导航、品牌、fixture root、provider、model、routing group 均从 ProductProfile 读取。

禁止模式：

- 在页面、service 或 repository 中散布新的环境变量判断；
- 按路由名称猜产品；
- 把产品模式当作权限校验；
- 在 default=false 时改变 TopicEye 旧 API 语义。

## 数据权威矩阵

| 数据 | 权威 | PostgreSQL 可否拥有 | 说明 |
| --- | --- | --- | --- |
| explosion facts/rank | 版本化 Rardar artifact | 否 | pointer + digest + strict Schema |
| evidence provenance | Rardar artifact | 否 | 不允许 DB 补造来源 |
| artifact revision | pointer | 只可引用 | Job 保存创建时 revision，不可回写 |
| RequirementProfile | PostgreSQL Job | 是 | 用户可编辑、可确认 |
| Job state/history | PostgreSQL | 是 | durable control plane |
| AI attempts/usage/errors | PostgreSQL | 是 | 不含 Key，不含自由文本正式 artifact |
| quick/deep result | PostgreSQL POC Job | 是 | 只引用版本化 candidate fixture |
| TopicEye ContentItem | TopicEye legacy product | 否，不能承载 repository facts | 保持隐藏，不强行复用 |

## Slice A 请求一致性

`GET /api/v1/rardar/explosion-board` 的一次请求执行：

1. 加载一次 `current.json`；
2. 解析安全相对路径；
3. 拒绝 symlink 和 root escape；
4. 读取一个 revision；
5. 校验 SHA-256；
6. strict Schema 校验和 rank contract；
7. 以该 revision 组装所有 AI payload；
8. 返回带 `artifactRevision` 的单代响应。

AI 是附加槽位。单项目 AI timeout、429、5xx、invalid JSON、Schema mismatch 或 circuit open 都只降低该槽位，不改变 HTTP 200 的事实榜。artifact 本身损坏时才返回 503，且不回退到 PostgreSQL 或 flat score。

## Slice B AI 调用链

```text
Rardar scene + requested effort
→ TopicEye model route lookup
→ global circuit breaker
→ response cache（namespace 包含 scene、route 与 reasoning effort）
→ model failover / cooldown
→ token + request rate limit
→ concurrency semaphore
→ deterministic Mock Sub2API
→ TopicEye usage log
→ Rardar local JSON + Schema validation
→ rardar_ai_requests audit row
```

Mock provider 固定 `gpt-5.6-sol`，只在内存中生成确定性响应。`api.cosflow.icu/mock-no-network` 是非敏感标识，不是网络 endpoint。任何真实 Key 都不在配置、数据库、Job、浏览器、日志或 PR 中。

## Slice C durable Job

API 负责创建、读取、确认、重试和删除 Job；repository 只访问自己的表；service 编排状态；独立 Worker 领取和执行。API 不直接操作 ORM，repository 不跨 repository import，符合 TopicEye 分层约束。

并发边界：

- `FOR UPDATE SKIP LOCKED` 保证单个 Job 同时只被一个 Worker 领取；
- lease 允许进程退出后的任务重新领取；
- state history 追加，不用当前 state 冒充历史；
- Job 失败保存 `retry_state`；
- Worker 的短暂数据库错误只记录并退避，不让常驻进程永久退出；
- xhigh 比较一次接收同一 RequirementProfile 和最多 5 个标准化候选。

## 数据库 migration

新增 migration `4d8a71c9f201`，down revision 是 pinned upstream 的 `c003bd551911`。upgrade 新建两张 POC 表和索引，downgrade 只删除这两张表。

Windows 真实 migration 暴露了 upstream `alembic.ini` 注释中的 Unicode em dash 会被 cp936 解码失败。POC 只把该注释替换为 ASCII `-`，不改变 migration 配置或数据库语义。

完整 Windows 回归还验证了 DuckDB 1.2.2 的 PostgreSQL extension artifact 必须按官方名称 `postgres_scanner` 加载，连接语义仍为 `ATTACH ... TYPE postgres`。本地离线扩展只保存在忽略的 runtime 目录，不进入 PR。

## 安全与故障隔离

- 当前代码基线是 fork main `f1c80188de7f05ba4285de48f962b7b31656d930`（PR #2），固定 FastAPI `0.133.0`、Starlette `1.3.1`、cryptography `50.0.0`，并通过 `pip-audit = 0` 与 main `security-scan`；
- 所有服务仅监听随机 `127.0.0.1` 端口；
- 不占用 Rardar 3000/3002；
- fixture 是代码库内只读事实源，测试切换使用临时副本；
- Worker 不持有 artifact 写权限，也不发布 pointer；
- Mock provider 没有 HTTP client 或 credential；
- frontend 只通过同源 rewrite 访问 backend；
- admin 继续使用 TopicEye 原有认证和视觉壳；
- default profile 不注册可见 Rardar 产品壳，POC API 返回 404。
- product mode 不隐式更改 scheduler/cache/seed/DuckDB 开关；隔离启动命令显式关闭它们。

该安全基线只解除旧依赖阻塞。真实 Provider、正式 scheduler、约 930.7 MB 资源包络、Production 备份与回滚仍不在 POC 已验证边界内。

## 正式融合前仍需设计

1. 用 Rardar generation loader 替换 POC fixture adapter，保留完全相同的一请求一代合同；
2. AI durable queue 的生产 lease、backlog、idempotency 和 dead-letter 设计；
3. 真实 Sub2API capability/security probe；
4. TopicEye 上游升级策略和定期 rebase 审计；
5. Runtime 进程拓扑、资源上限、备份和恢复演练；
6. POC Job 结果到正式 Rardar artifact 的审核发布协议；
7. 将 product-mode 相关启动开关收敛成一个可审计 runtime profile，避免运维漏配。
