# Rardar UI Migration POC

## 视觉权威

UI 以只读 Rardar baseline `e21c5e258c63140ff941434e0f57514893258b42` 为视觉权威，没有把 TopicEye 现有内容后台直接换 Logo。保留的 Rardar 特征：

- 白底、明亮蓝色主色、低饱和浅蓝页面底；
- 顶部品牌与横向导航；
- 大字号事实型 hero；
- 事实卡、覆盖说明和明确更新时间；
- 手机端固定六项底部导航；
- AI 判断与事实字段在视觉上分区。

`/admin` 仍由 TopicEye `AdminSidebar`、`AdminTopBar`、认证和权限壳接管。Rardar 产品模式只替换非 admin 产品 chrome。

## 信息架构

| 导航 | 路由 | POC 状态 | 行为 |
| --- | --- | --- | --- |
| 今日 | `/` → internal `/rardar-poc` | 完整 | audited Top 5 + pending 3 |
| 动态 | `/signals` | 诚实占位 | 不伪装已实现 |
| 发现 | `/discover` | 诚实占位 | 不声称扫描全 GitHub |
| 找项目 | `/find-project` | 完整 | durable quick/deep flow |
| 候选池 | `/candidates` | 诚实占位 | 不建立假数据页面 |
| 观察列表 | `/watchlist` | 诚实占位 | 不提前做资产库 |
| POC diagnostics | `/admin/rardar-poc` | 完整、受 admin 保护 | TopicEye admin 风格 |

Root 使用 `beforeFiles` rewrite，仅在 `RARDAR_PRODUCT_MODE=true` 时将 `/` 映射到 server-rendered Rardar 页面；default=false 时 upstream `app/page.tsx` 完全保持原行为。

## 爆发榜语义

页面明确显示：

- 主榜是 fixture 的精确 24h Star delta；
- AI 不改变排名；
- “AI 爆发原因判断”不是确定事实；
- 新项目立即进入“新入榜待验证”，但不进入精确主榜；
- artifact revision、候选召回、查询和观察覆盖；
- artifact 损坏时 fail closed，不显示 TopicEye score 兜底。

## 找项目交互

1. 用户输入自然语言需求，可选公开 GitHub URL；
2. API 返回 queued Job，页面轮询持久状态；
3. high 生成 RequirementProfile；
4. 用户可编辑目标、must-have、preferred、constraints 和 acceptance checks；
5. 确认后进入 xhigh 5→3 横向比较；
6. 结果显示复用类型、原因、must-have 覆盖、缺失/未知能力、技术兼容、集成成本、工程证据、evidenceRefs、许可证风险和下一验证动作；
7. failed 状态保留 Job，并提供显式 retry；
8. URL 保存 `jobId`，刷新可恢复进度和结果。

## 响应式验证

真实浏览器在三档 viewport 验证，无横向溢出：

| 页面 / 状态 | 1440×900 | 768×1024 | 375×812 |
| --- | --- | --- | --- |
| 爆发榜 | [截图](./screenshots/explosion-board-1440x900.png) | [截图](./screenshots/explosion-board-768x1024.png) | [截图](./screenshots/explosion-board-375x812.png) |
| Find quick | [截图](./screenshots/find-project-quick-1440x900.png) | [截图](./screenshots/find-project-quick-768x1024.png) | [截图](./screenshots/find-project-quick-375x812.png) |
| Find ready | [截图](./screenshots/find-project-ready-1440x900.png) | [截图](./screenshots/find-project-ready-768x1024.png) | [截图](./screenshots/find-project-ready-375x812.png) |

桌面使用横向导航和双栏事实区；平板隐藏桌面导航并显示固定底栏；手机 hero、指标、卡片和 Job 信息全部单列。底栏可能遮住滚动内容的末端视觉区域，因此页面保留额外 bottom padding。

## 可访问性与 SSR

- 语义 heading、banner、main、nav、article 和 label；
- 桌面与移动 nav 都有独立 aria label；
- 表单使用真实 label；
- skip link 指向 `#main-content`；
- focus ring 延续 TopicEye 全局可见策略；
- `/` 的榜单事实由 Next Server Component 获取并出现在 server-rendered HTML；
- Find Project 是 client interaction，但 Job 状态来自 PostgreSQL，不依赖浏览器内存。

## 仍需正式迁移的 UI 工作

- 用真实 audited generation 替换 fixture；
- 为历史/退出项目定义 canonical detail route；
- 统一 loading、degraded、empty 和 artifact-invalid 设计系统；
- 在正式 auth/device 模型下保存查询和 opt-in 个性化；
- 对 admin diagnostics 增加生产只读权限和审计；
- 用 Rardar 的真实组件 token 替换少量 POC Tailwind inline value。
