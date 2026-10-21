# Trendshift 当前 Flight 资源引用续修

PR #74 合并后、生产切换前，Runtime 的一次 source-only 实测返回 `trendshift_date_assets_missing`。旧生产后端和 PR #77 前端未切换。以 `a8ff472` 为基线补齐此解析缺口，保留 Find 和安全依赖修正。

## 已确认原因与最小修正

2026-10-21 保存的真实公开首页使用 Flight `$hex` 字符串记录引用声明 chunk，而非在组件 import 中直接写 URL。实际日历组件解析得到 24 个同源资产。初查的另一个组件有 18 个依赖，不代表日历组件的完整范围。

只解析当前 payload 内的一层字符串引用，缺失、非字符串或链式引用明确失败；路径仍限制为同源 `/_next/static/chunks/` JavaScript，无执行脚本或追踪任意 import。声明上限调整为 32 以覆盖实际 24 项，单资产 1 MB 与日期请求整体 120 秒截止不变。

## 验证

- 新增回归先在旧实现复现失败，再修正；覆盖 24 项引用及缺失、链式、错误类型引用。既有路径、歧义、日期、超时测试保留。
- 保存的真实首页通过实际 `_fetch_ended_trendshift` 路径完成同源资产读取、唯一 action 发现及日期 POST：`sourceDate=targetPeriodDate=2026-10-20`、`acquisitionMode=ended_utc_day`、25 个仓库、healthy。响应摘要 `47a208454db276853accff0dbffa0455764752034af27a4fce49a30e6131ac5c`。
- 原始公开首页及 JS 仅保存在本机临时诊断目录，不提交整页内容；测试为明确标注的最小结构复现。
- 未写生产榜单、预算或资料；Provider 新增 0。本地来源读取成功不等于生产日程已恢复，发布后的源站读取和下一自然周期分别记录。

沿用现有 CI、Linux artifact 和 Runtime 后端增量发布流程，不新增采集入口或调度。
