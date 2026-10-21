# 必要依赖安全补丁（2026-10-21）

## 范围

独立于 Find 请求限额 PR #75；基于 main `34d5478`。不修改认证、模型路由、预算、生产配置或安全扫描门禁，不执行真实 Provider 请求。

## 修正

- LiteLLM 1.95.0 → 1.95.1（GHSA-3cv6-jpf6-8222）。
- Next.js 16.3.3 → 16.3.8，ESLint 配置同步至 16.3.8。
- 锁文件更新已发布的兼容安全版本：sharp 0.35.5、source-map-js 1.2.2、brace-expansion 1.1.21 / 5.0.12、Vite 8.3.5 及相应绑定。
- 未使用 `npm audit fix --force`，未忽略漏洞或降低扫描等级。

## 验证与发布阻断

- 前端 TypeScript 检查、Next production build 通过，31 个测试文件 / 352 项通过。
- 独立 LiteLLM 1.95.1 overlay 的 Find / 控制 / timeout / structured 模拟回归 122 项通过；未修改共享开发环境，完整 PostgreSQL 回归留给 CI。
- npm 生产依赖审计为 0 漏洞；这不替代完整依赖门禁。
- 完整 npm audit 仍失败：braces 3.0.3 的 GHSA-vfj7-8cjw-p6xm 尚无正式修补版本，其 micromatch → fast-glob → @next/eslint-plugin-next → eslint-config-next 链合计报告 5 个高危条目。官方公告：https://github.com/advisories/GHSA-vfj7-8cjw-p6xm 。核对最新版 Next ESLint 插件 16.4.2 仍依赖 fast-glob，不能通过普通升级移除该链。
- 不采用 npm 建议的强制降级到 eslint-config-next 14，也不删除有效 lint 规则。安全门禁未通过前保持 Draft，不发布。
- 真实 Find 验收仍保留原累计 2/5、最多剩余 3 次；本次依赖验证新增 Provider 请求为 0。

完整后端与 production 浏览器兼容性以本 PR 最终 HEAD 的 CI 为准；CI 的模拟响应浏览器测试不等于线上真实 Find 验收。
