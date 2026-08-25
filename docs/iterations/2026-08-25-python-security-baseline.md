# Python 安全依赖基线（2026-08-25）

## 结论与边界

- 基线：fork `main` 与 pinned upstream `main` 均为 `8b559895c6e3547550a85ac561cfee4a42113448`。
- 分支：`fix/python-security-baseline`。
- 结果：FastAPI、Starlette 与 cryptography 的已知漏洞归零；默认 TopicEye 与隔离的 Rardar POC 组合均通过回归。
- 本迭代不修改运行时代码、Pydantic、数据库模型、Alembic migration、前端、workflow 或 POC PR #1。
- POC PR #1 的固定 head `d37a74ca89d5eea8e5feabc86af99930ba975e07` 仅用于仓库外 scratch 演练，原分支和 PR metadata 未修改。
- 未访问 Production，未使用真实 OAuth credential，未调用真实 AI provider。

## 依赖基线

审计环境使用全新 Python 3.12.13 虚拟环境、pip 26.2.1 与 pip-audit 2.7.3。完整解析结果和审计 JSON 保存在仓库外临时证据目录，不提交安装环境或凭据。

| 依赖 | 升级前 | 选定版本 | 说明 |
| --- | --- | --- | --- |
| FastAPI | `0.115.14` | `0.133.0` | 第一个解除 Starlette `<1.0.0` 上限并正式支持 Starlette 1.x 的最小 FastAPI 边界 |
| Starlette | resolver 得到 `0.46.2` | `1.3.1` | 显式 pin 为 FastAPI 的安全兼容边界；不是独立框架替代 |
| cryptography | `45.0.7` | `50.0.0` | 覆盖全部已知 cryptography finding 的最低共同修复边界 |
| Pydantic | `2.10.4` | `2.10.4` | resolver 与行为测试均未要求升级 |

参考来源仅使用官方材料：[FastAPI release notes](https://fastapi.tiangolo.com/release-notes/)、[FastAPI PyPI](https://pypi.org/project/fastapi/)、[Starlette PyPI](https://pypi.org/project/starlette/)、[cryptography PyPI](https://pypi.org/project/cryptography/) 和 GitHub Advisory Database。

## 初始 advisory 映射

基线环境共有 14 个 finding。TopicEye 直接使用 cryptography 的 Fernet，加密路径也被 Authlib 间接依赖；代码中未发现对下表涉及的其他 cryptography 高级原语作直接调用。Starlette 的请求、表单和 middleware 栈属于真实攻击面，因此即使某一具体原语未被直接调用，也不对 advisory 做忽略或 allowlist。

| Package / installed | Advisory | 受影响范围 | 官方修复版本 | TopicEye 使用面 | 升级后证据 |
| --- | --- | --- | --- | --- | --- |
| cryptography 45.0.7 | [GHSA-p423-j2cm-9vmq](https://github.com/advisories/GHSA-p423-j2cm-9vmq) / PYSEC-2026-36 | `>=45.0.0,<46.0.7` | `46.0.7` | Fernet 直接使用、Authlib 间接使用；未发现对应高级原语的直接调用 | cryptography 50.0.0、Fernet/Authlib 全套测试、pip-audit 0 |
| cryptography 45.0.7 | [GHSA-m959-cc7f-wv43](https://github.com/advisories/GHSA-m959-cc7f-wv43) / PYSEC-2026-35 | `<46.0.6` | `46.0.6` | 同上 | 同上 |
| cryptography 45.0.7 | [GHSA-r6ph-v2qm-q3c2](https://github.com/advisories/GHSA-r6ph-v2qm-q3c2) / PYSEC-2026-2141 | `<=46.0.4` | `46.0.5` | 同上 | 同上 |
| cryptography 45.0.7 | [GHSA-g6cj-pr64-35w5](https://github.com/advisories/GHSA-g6cj-pr64-35w5) / PYSEC-2026-3552 | `>=44.0.0,<50.0.0` | `50.0.0` | 同上 | 同上 |
| cryptography 45.0.7 | [GHSA-jwv3-5hgf-82ww](https://github.com/advisories/GHSA-jwv3-5hgf-82ww) / PYSEC-2026-3553 | `<=48.0.0` | `49.0.0` | 同上 | 同上 |
| cryptography 45.0.7 | [GHSA-m2h6-j472-rp4c](https://github.com/advisories/GHSA-m2h6-j472-rp4c) / PYSEC-2026-3554 | `<=48.0.0` | `49.0.0` | 同上 | 同上 |
| cryptography 45.0.7 | [GHSA-537c-gmf6-5ccf](https://github.com/advisories/GHSA-537c-gmf6-5ccf) | `>=0.5.0,<48.0.1` | `48.0.1` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-86qp-5c8j-p5mr](https://github.com/advisories/GHSA-86qp-5c8j-p5mr) / PYSEC-2026-161 | `<=1.0.0` | `1.0.1` | 请求、表单、multipart、middleware、URL 和 response 栈 | Starlette 1.3.1、专项行为测试、全量回归、pip-audit 0 |
| Starlette 0.46.2 | [GHSA-82w8-qh3p-5jfq](https://github.com/advisories/GHSA-82w8-qh3p-5jfq) / PYSEC-2026-249 | `>=0.4.1,<1.3.1` | `1.3.1` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-jp82-jpqv-5vv3](https://github.com/advisories/GHSA-jp82-jpqv-5vv3) / PYSEC-2026-248 | `<1.3.0` | `1.3.0` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-7f5h-v6xp-fcq8](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8) / PYSEC-2026-1942 | `>=0.39.0,<=0.49.0` | `0.49.1` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-2c2j-9gv5-cj73](https://github.com/advisories/GHSA-2c2j-9gv5-cj73) / PYSEC-2026-1941 | `<0.47.2` | `0.47.2` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-wqp7-x3pw-xc5r](https://github.com/advisories/GHSA-wqp7-x3pw-xc5r) / PYSEC-2026-2281 | `<1.1.0` | `1.1.0` | 同上 | 同上 |
| Starlette 0.46.2 | [GHSA-x746-7m8f-x49c](https://github.com/advisories/GHSA-x746-7m8f-x49c) / PYSEC-2026-2280 | `<1.1.0` | `1.1.0` | 同上 | 同上 |

## 实际攻击面

| 能力 | 分类 | TopicEye 证据 / 验证 |
| --- | --- | --- |
| FastAPI app、APIRouter、lifespan | USED | 默认应用启动、全量 API 测试、真实 HTTP |
| CORS、BaseHTTPMiddleware | USED | 新增中间件行为回归与全量测试 |
| BackgroundTasks、RedirectResponse | USED | 全量后端测试；OAuth route 保持禁用时安全失败 |
| UploadFile、File、multipart | USED | 有效 OPML 风格上传、异常 multipart、字段和大小限制 |
| `request.form()` / multipart parser | INDIRECTLY_USED | 表单专项行为回归 |
| cookies、`request.url` / `base_url` | USED | URL authority/path 边界测试和 OAuth callback 构造路径 |
| OpenAPI / TestClient | USED | OpenAPI 生成及 health、login、sources、import-opml 路由存在性 |
| Authlib / OAuth | USED | Authlib import、provider 配置禁用态、OAuth service 与真实公开 GET；没有访问真实 provider |
| Fernet | USED | `secret_store.py` 直接使用；现有 secret/API-key 加解密回归通过 |
| StaticFiles / FileResponse | NOT_USED | 应用中未发现对应挂载或文件响应；不伪造无关测试 |
| StreamingResponse / client-disconnect streaming | NOT_USED | 未发现对应产品路径 |
| WebSocket | NOT_USED | 未发现 WebSocket route |
| SessionMiddleware / TrustedHostMiddleware | NOT_USED | 未配置 |
| mounted sub-apps / HTTPEndpoint / Starlette Route | NOT_USED | 未发现对应应用面 |
| cryptography PKCS7 / X.509 / SECT 等高级原语 | NOT_USED | 未发现直接 import；仍整体升级到无 finding 版本 |

## 候选解析与选择

两个候选均在独立 Python 3.12 环境中由 resolver 正常安装，没有使用 `--no-deps`：

| 候选 | FastAPI | Starlette | cryptography | Pydantic | 结果 |
| --- | --- | --- | --- | --- | --- |
| A：全部修复下限的最小兼容组合 | 0.133.0 | 1.3.1 | 50.0.0 | 2.10.4 | pip check PASS、pip-audit 0、93/93 受影响面测试 PASS |
| B：执行时最新稳定组合 | 0.141.1 | 1.6.0 | 50.0.0 | 2.10.4 | pip check PASS、pip-audit 0、同一 93/93 测试 PASS |

选择 A。FastAPI 0.133.0 是允许 Starlette 1.x 的最小官方兼容边界；Starlette 1.3.1 和 cryptography 50.0.0 分别是覆盖本次全部 finding 的最低共同边界。候选 B 没有带来本任务所需的额外安全收益，因此不扩大升级面。除这三个 package 外，没有修改直接依赖。

## 新增行为回归

`backend/tests/test_python_security_baseline.py` 固化以下合同：

1. 三个安全边界版本必须作为一组安装；
2. Host 与 path-like authority 不得混淆；
3. URL-encoded form 的字段数与单字段大小限制生效；
4. 有效 multipart 上传成功，异常 multipart 返回 400；
5. CORS 与 BaseHTTPMiddleware 行为保持；
6. 默认应用 OpenAPI 仍包含 health、login、sources 与 OPML import。

## 验证矩阵

### 最终安全环境

- Python 3.12.13，pip 26.2.1，pip-audit 2.7.3。
- `pip check`：PASS。
- 实际安装环境 `pip-audit` 与 JSON audit：0 known vulnerabilities；未忽略任何 advisory。
- `ruff check`：PASS；本次 Python 变更使用 CI 固定 Ruff 0.6.9 执行 `ruff format --check`：PASS。
- API layering：PASS。

### 默认 TopicEye

- Linux/glibc Python 3.12 全量 backend：884 passed、0 skipped、0 failed；首次并发测试出现一次 SQLite shared-memory 偶发提交竞争，隔离重跑 5/5 与重置数据库后的完整重跑均通过。
- Windows 诊断运行出现 11 failures + 2 errors，均由已存在的平台差异导致（timer rounding、缺少 `resource`、CP936 读取 UTF-8 Alembic）；旧依赖基线复现相同节点，因此不属于升级回归。
- PostgreSQL 16.15：空库 `alembic upgrade head` 到 `c003bd551911`，重复执行 no-op，应用启动 PASS。
- 真实 backend HTTP（随机 loopback）：health/OpenAPI/OAuth provider 列表/sources/权限边界/multipart 权限边界/404/422 均符合合同，无 500。
- Frontend：TypeScript PASS；Vitest 140/140；coverage 95.34% statements / 92.38% branches；production build PASS（40 routes）；npm audit 0。
- 默认首页 HTTP 200，标题仍为“选题雷达 · 创作者选题情报站”。

### Rardar POC scratch

- 组合方式：安全代码树临时 commit `6c1425121eca5f892d8108ca04ac382703306174`，对 POC 精确 head `d37a74ca89d5eea8e5feabc86af99930ba975e07` 执行 detached、`--no-commit` merge；结果 index tree 为 `3cb131f534bbdd1b6b824069e899167ba20bb975`，未 push、未改 PR #1。
- Windows checkout 会把已签名 fixture JSON 转为 CRLF 并导致 digest mismatch；最终演练从 Git blob 原字节导出 artifact，验证的是 pointer 所绑定的精确 LF 内容。该问题是 scratch checkout 环境差异，不是依赖兼容问题。
- Backend 全量：895/895 PASS；POC 专项：11/11 PASS。
- PostgreSQL 16.15：空库升级 `c003bd551911 -> 4d8a71c9f201`，重复升级 no-op，真实启动 PASS。
- Rardar mode build：PASS；default TopicEye build：PASS。
- Frontend：TypeScript PASS；Vitest 142/142；npm audit 0。
- 真实 HTTP：health、profile、事实榜、frontend proxy 与 SSR 首页均 200；AI timeout 时事实 Top 5 保留且不改变名次。
- Mock AI：medium/high/xhigh 均通过 `mock_sub2api` 使用 `gpt-5.6-sol`，diagnostics 明确 `networkCalls=false`。
- Find Project：独立 worker 完成 quick candidates、确认、3 个 deep results、持久化和 reload。
- Playwright：7 passed、1 个 desktop 项目中的 mobile-only 合同按设计 skipped；桌面和移动关键流均通过。
- 分类：`POC_COMPATIBLE`；不需要 POC 专属兼容修复。

## 回滚合同

如需短期诊断，revert 本安全升级 commit 并恢复旧 `backend/requirements.txt` 即可。本 PR 没有 migration、模型或数据格式变更，因此不执行数据库 downgrade。

旧版本带有已知漏洞，回滚状态只能用于隔离故障，不得视为可部署的安全状态。恢复服务前必须重新选择一个 `pip-audit = 0` 的兼容组合并完成同等验证。

## 未解决风险与后续事项

- FastAPI 0.133.0 在当前 TestClient/httpx 组合下发出未来迁移到 `httpx2` 的弃用警告；当前行为测试和全量套件均通过。httpx 迁移应单独评估，不混入本安全 PR。
- requirements 仍是无统一 lock 的 pin + resolver 模式；本次通过显式 pin 安全边界收敛风险，完整锁定策略属于独立依赖治理任务。
- Windows 全量测试仍有既有平台基线问题；应独立改进跨平台测试工具链，不能在本 PR 顺带重写测试。
- 未使用的 StaticFiles、streaming、WebSocket 和 cryptography 高级原语没有编写伪测试；若未来引入这些能力，应在同一变更中增加对应安全合同。
- advisory 集合会继续演化；CI `security-scan` 必须保持阻断，不能用 ignore/allowlist 代替升级。
