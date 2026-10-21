# 必要依赖安全补丁（2026-10-21）

## 范围

独立于 Find 请求限额 PR #75；基于 main `34d5478`。不修改认证、模型路由、预算、生产配置或安全扫描门禁，不执行真实 Provider 请求。

## 修正

- LiteLLM 1.95.0 → 1.95.1（GHSA-3cv6-jpf6-8222）。
- Next.js 16.3.3 → 16.3.8，ESLint 配置同步至 16.3.8。
- 锁文件更新已发布的兼容安全版本：sharp 0.35.5、source-map-js 1.2.2、brace-expansion 1.1.21 / 5.0.12、Vite 8.3.5 及相应绑定。
- 未使用 `npm audit fix --force`，未忽略漏洞或降低扫描等级。

## 根因处理与验证

- 前端 TypeScript 检查、Next production build 通过，31 个测试文件 / 352 项通过。
- 独立 LiteLLM 1.95.1 overlay 的 Find / 控制 / timeout / structured 模拟回归 122 项通过；未修改共享开发环境，完整 PostgreSQL 回归留给 CI。
- npm 生产依赖审计为 0 漏洞；这不替代完整依赖门禁。
- 初次完整审计仍有 braces 3.0.3 无修补版依赖链。后续定向核对确认 Next ESLint 仅用 `globSync(pattern, {onlyDirectories:true})` 发现项目根目录。以 scoped override 将该依赖替换为本地小型目录适配器，内部调用受维护的 tinyglobby 0.2.17；删除实际漏洞依赖链，不抑制审计。
- 适配器保留 literal / brace / wildcard / 目录数组 / 绝对路径 / descendant-only 语义，关闭 tinyglobby 默认的隐式目录扩展。真实 getRootDirs 与 Next 内链检查规则回归证明原规则仍报告违规。它不声称兼容 fast-glob 全 API。
- 干净 npm ci 与完整 npm audit 为 0 漏洞。Docker 安装依赖前复制适配器，避免本地可用但镜像缺文件。
- 不采用强制降级，不删除 lint 规则。保留现有 CI，通过后再协同发布。
- 真实 Find 验收仍保留原累计 2/5、最多剩余 3 次；本次依赖验证新增 Provider 请求为 0。

完整后端与 production 浏览器兼容性以本 PR 最终 HEAD 的 CI 为准；CI 的模拟响应浏览器测试不等于线上真实 Find 验收。
