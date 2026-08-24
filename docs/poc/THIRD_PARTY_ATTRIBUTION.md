# Third-Party Attribution

## TopicEye

- Project: TopicEye
- Original repository: <https://github.com/fxbin/TopicEye>
- POC fork: <https://github.com/Brilliant666/TopicEye>
- Pinned upstream commit: `8b559895c6e3547550a85ac561cfee4a42113448`
- Current secure fork base: `f1c80188de7f05ba4285de48f962b7b31656d930`（PR #2）
- License: Apache License 2.0
- License file: repository root `LICENSE`（保持原样）

本 POC 保留原始 Git 历史、作者归属和 fork 关系。`8b559895...` 继续表示原始 upstream provenance；`f1c80188...` 是 fork 上独立审查并合入的 Python 安全基线，不伪装成 upstream 提交。`poc/rardar-product-shell` 上的修改由 Rardar POC 添加，主要包括 ProductProfile、Rardar adapter/API/Worker、两张 POC 控制面表、产品壳、fixture、测试和本目录文档。

Apache-2.0 允许在遵守许可证条款的前提下使用、修改和分发。正式分发时应继续随产品提供 LICENSE，并检查上游是否新增 NOTICE 或其他第三方归属文件。本文件是工程归属记录，不构成法律意见。

## PostgreSQL

POC 使用 PostgreSQL 16.15 Windows binary archive 在仓库外运行。二进制、data directory 和下载包均未加入 Git。PostgreSQL 使用 PostgreSQL License；详情见 <https://www.postgresql.org/about/licence/>。

## Rardar design authority

Rardar 的产品名、导航、视觉语言和产品语义来自同一所有者的只读仓库 baseline：

- Repository: <https://github.com/Brilliant666/rardar>
- Commit: `e21c5e258c63140ff941434e0f57514893258b42`

POC 没有修改该仓库，也没有复制其运行时数据、credential、D1 或 Production generation。

## JavaScript and Python dependencies

依赖版本和传递依赖锁定在：

- `frontend/package-lock.json`
- `backend/requirements.lock`

POC 新增的直接开发依赖是 `@playwright/test`，只用于本地真实浏览器测试。依赖本身的许可证由各自包元数据约束；正式发布前继续执行 dependency/security audit，并按需要汇总 NOTICE。

## No provider endorsement

`Mock Sub2API`、`gpt-5.6-sol` 和 `api.cosflow.icu/mock-no-network` 只描述一个网络隔离的测试合同，不表示 OpenAI、Sub2API 或任何上游提供方认可、验证或支持本 POC。没有真实 provider request、API Key 或 credential 被使用或提交。
