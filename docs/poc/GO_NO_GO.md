# TopicEye as Rardar Platform: GO / NO-GO

## 最终决定

```text
GO_PLATFORM_FUSION
```

该决定只批准下一阶段的受控平台融合设计，不批准合并本 POC、部署、真实 AI 接入或数据迁移。

## 硬门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 合法 fork / 原历史 / Apache-2.0 | PASS | fork 关联 upstream，LICENSE 未改 |
| 固定 upstream provenance | PASS | 原始 upstream `8b559895...`，无来源漂移 |
| Python 安全基线 | PASS | fork main `f1c80188...`（PR #2）；FastAPI 0.133.0 / Starlette 1.3.1 / cryptography 50.0.0 |
| Rardar baseline read-only | PASS | `e21c5e2...` 未切换、未写入 |
| 真实 PostgreSQL | PASS | PostgreSQL 16.15 + Alembic head |
| artifact 仍是事实权威 | PASS | pointer/hash/Schema/atomic switch tests |
| AI 不改变榜单 | PASS | success/failure HTTP 行为测试 |
| durable Job + 独立 Worker | PASS | quick/deep/failure/retry/reload |
| 无真实 Key / 网络 AI | PASS | deterministic Mock，无 HTTP client |
| default TopicEye 不回归 | PASS | backend/frontend/test/build gate |
| Rardar 产品壳和 admin 隔离 | PASS | product routes + original admin shell |
| 三档响应式浏览器证据 | PASS | 9 张 viewport 截图 |
| 隔离端口与进程清理 | PASS | 仅随机 loopback；61981–61984 与 55432 均已释放，无 POC 残留进程 |

## 加权评分

评分阈值：85 以上且硬门禁全绿才允许 `GO_PLATFORM_FUSION`；70–84 为 `ADAPT_MODULES_ONLY`；低于 70 或事实边界失败为 `NO_GO`。

| 维度 | 权重 | 得分 / 10 | 加权 | 判断 |
| --- | ---: | ---: | ---: | --- |
| 事实与 generation 边界 | 20 | 10 | 20.0 | adapter 能保持 fail closed |
| durable control plane | 15 | 9 | 13.5 | PG Job/lease/retry 可直接演进 |
| AI runtime 可复用度 | 15 | 8 | 12.0 | cache/failover/circuit/usage 成熟；真实 provider 未 probe |
| Rardar 产品壳适配 | 15 | 9 | 13.5 | nav、hero、事实卡、Find flow 已成立 |
| default TopicEye 兼容 | 10 | 9 | 9.0 | central profile，旧模块不删除 |
| 运行与资源成本 | 10 | 7 | 7.0 | 单机可运行；平台基线偏重，需生产限额 |
| 变更隔离/上游同步 | 10 | 8 | 8.0 | adapter 面清晰；长期 fork 成本仍存在 |
| 法律与归属 | 5 | 10 | 5.0 | Apache-2.0 与归属保留 |
| **合计** | **100** |  | **88.0** | **GO** |

## 为什么不是 ADAPT_MODULES_ONLY

只复制 Job 或 LLM 模块会丢失 TopicEye 已经打通的 repository/service、migration、admin、API 和 frontend 运维组合，也会制造第二套相似基础设施。纵向 POC 证明这些能力可以在 central profile 下共同工作，且不要求把事实权威迁入 TopicEye 数据库。

## 为什么不是无条件 GO

以下风险仍然真实：

- TopicEye 是内容平台，Rardar 是 GitHub 项目情报产品，领域模型不能混用；
- frontend/backend/worker/PostgreSQL 的常驻资源明显高于当前轻量 Rardar；
- fork 需要长期跟踪 upstream 安全与 migration 变化；
- 真实 Sub2API、gpt-5.6-sol、xhigh 和 Structured Outputs 尚未验证；
- POC fixture 不是生产 observer/generation；
- TopicEye auth 和 Rardar device/user 模型没有统一。
- Python 安全基线已由 PR #2 独立升级并合入 fork main：`pip-audit = 0`，main 的 `security-scan` 已通过。后续 advisory 演化和无统一 lock 的依赖治理仍需持续跟踪。
- `RARDAR_PRODUCT_MODE` 尚未自动收敛 scheduler/cache/seed/DuckDB 启动开关，正式 runtime profile 需要消除漏配风险。

```text
POC_SECURITY_BASELINE = RESOLVED
```

这只解除原 POC 基于旧依赖产生的安全红灯，不改变本页的资源、真实 Provider、正式 scheduler、Production 备份与回滚等未解决风险，也不使本 Draft POC 具备生产或合并资格。

## GO 的约束条件

下一阶段只有同时遵守以下条件才延续 GO：

1. 继续以 Rardar artifact/generation 为事实唯一权威；
2. 第一个正式融合 PR 只建立平台骨架和 adapter，不迁移 Production；
3. Repository 使用独立领域模型，不进入 ContentItem；
4. AI 默认 disabled，真实调用前完成 capability/security probe；
5. AI Worker 与 Website/Scheduler 进程隔离；
6. upstream 固定版本、归属和 Apache-2.0 合规检查进入 CI；
7. default TopicEye 和 Rardar mode 都是 required test matrix；
8. 每个融合 PR 独立、可回滚，不顺带删除隐藏模块；
9. 先定义正式资源预算、备份和恢复，再考虑 Production；
10. POC PR 永远保持 Draft，不合并。

## 建议的下一步

创建独立 RFC（不是本 POC 分支），定义：

- 正式 Rardar generation adapter；
- TopicEye fork/upstream maintenance policy；
- AIJob v1 contract 和 Worker process boundary；
- user/device/auth mapping；
- production resource envelope；
- 分阶段迁移和 rollback protocol。

若任何后续实测要求 PostgreSQL 接管事实名次、必须把 Repository 强制映射为 Content，或 default TopicEye 无法继续验证，则决定自动降级为 `ADAPT_MODULES_ONLY`。
