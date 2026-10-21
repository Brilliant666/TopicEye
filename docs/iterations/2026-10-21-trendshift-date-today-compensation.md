# Trendshift 指定日采集与 Today 补偿资格

基线：`34d5478b3c74183728fb7ca7f6c7ac9b657a74d0`（PR #73）。仅开发与离线验证；生产核对、增量发布和自然运行验收由 Runtime 负责。

## 原因与证据边界

- 旧日期 action 发现依赖 `initialData` 首字段、空组件 key 和最后四个 chunk；发现失败会把首页解析成 healthy。10/19 起的历史记录证实走了该回退，但没有当时 HTML/JS，不能确定是哪种网页变化。
- 日程只看已保存的总体停止原因。当前队列中的合法 Today 本身不会让 `historical_work` 返回历史名额用尽；缺口在资格或来源变化后，补偿仍沿用旧总体原因。没有项目级历史细节，不能断言 10/17 的 Today 项确实可重试。

## 修正

- 按 Flight JSON 解析组件引用和全部有界声明资产，不运行 JavaScript、不追踪任意 URL。最多 16 个同源 chunk、每个 1 MB，日期发现与 POST 合计最多 120 秒。跨 chunk 唯一命名 action 才允许日期请求；缺失、歧义、超时或日期错配返回明确失败，不以首页替代目标日。
- 旧 healthy 首页回执先验证摘要和原数据，再判为不满足指定日复用；仅在原有主轮/补偿机会中恢复。旧不可变榜单继续原哈希/投影校验，读取时标记日期未证实并抑制错误双榜标记。具体白名单失败码保留，任意异常正文不公开。
- 补偿使用原资料、每日 debit 和准入规则只读回查 Today/历史分域资格；来源恢复发布后再核对一次新集合。预算不足明确表示等待，不冒充无待处理。
- 原内容冷却命中记录为 deferred，不增加新的生成失败 debit；未触及的合法工作仍获得后续片机会。准入资格不等于已证明内容身份/冷却允许模型请求，下层校验继续生效。

不改变：GitHub 主增长优先、Trendshift 次选、>=200 门槛及排序；历史 3 项/日、模型 100 次/日和预留 10；09:00/11:00 最多两轮；原锁、预算、失败历史和内容校验。

## 验证与发布边界

测试均为明确标注的合成 HTML/Flight、MockTransport、模拟 Provider 和独立临时文件。覆盖真实 `run_refresh`/`historical_work`、回执保存与重新读取、旧快照、恢复后新 Today、每日 2/2、冷却、预算不足和重复补偿；不是只测试辅助函数。

相关测试入口：

```text
tests_rardar_adapter/test_trending_boards.py
tests_rardar_llm/test_daily_refresh_policy.py
tests_rardar_llm/test_daily_trendshift_recovery.py
tests_rardar_llm/test_trendshift_date_readback.py
tests_rardar_llm/test_material_work_allowance.py
tests_rardar_llm/test_material_deferred_rotation.py
tests_rardar_llm/test_refocus_daily_entry.py
tests_rardar_llm/test_daily_review_wiring.py
tests_rardar_llm/test_daily_round_audit.py
tests_rardar_llm/test_trending_primary_growth.py
tests_rardar_llm/test_trending_growth_projection.py
tests_rardar_selection/test_profile_cache_v2.py
```

本地最终相关回归：188 passed、1 skipped（既有可选验证），Ruff 与分层检查通过。必要 CI 绑定提交执行，结果以 PR 检查记录为准。

开发阶段真实模型、资料源、榜单抓取、Find、人工日程和生产操作均 0。当前真实 Trendshift 网页和新自然周期未验证；不把离线通过报告为生产恢复。沿用 `rardar-release-artifact.yml` 的 exact-SHA Linux 构建及 manifest，不新增发布系统。Runtime 必须继续核对真实 squash SHA/同 tree、镜像来源与生产容量门禁；本分支不操作服务器。
