import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarDailyOperations, { DailyExecutionSummary } from '@/components/RardarDailyOperations';

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/lib/api/_core', () => ({ request: state.request }));

describe('Rardar daily admin controls', () => {
  it('separates current publication, failed attempt, work debt and shared usage', () => {
    const html = renderToStaticMarkup(<DailyExecutionSummary budget={{ day: '2026-09-10', configuredLimit: 100, attempted: 8, remaining: 92, interactiveReserve: 10, earlyBackgroundLimit: 20, stageBreakdown: { project_profile: 5, news_quickread: 3 }, dailyStatus: { status: 'partial', scheduling: { workSlices: 2, sliceRequestLimit: 6, waitReason: 'interactive_reserve' }, modules: { discover: { status: 'failed', checked: 48, processed: 6, currentPublishedCount: 4, newlyPublishedTotal: 0, currentGenerationId: 'healthy', attemptGenerationId: 'failed-attempt', currentPending: 5, historyPending: 37 } } } }} />);
    expect(html).toContain('当前展示版本：healthy');
    expect(html).toContain('最新尝试版本：failed-attempt');
    expect(html).toContain('本轮新发布：0');
    expect(html).toContain('历史积压：37');
    expect(html).toContain('资讯中文阅读 3');
    expect(html).toContain('为手动操作保留额度');
    expect(state.request).not.toHaveBeenCalled();
  });
  it('explains daily shared limits and offline behavior without starting work during render', () => {
    const html = renderToStaticMarkup(<RardarDailyOperations />);
    expect(html).toContain('每日 08:30');
    expect(html).toContain('立即检查 / 补跑');
    expect(html).toContain('恢复日程');
    expect(html).toContain('未配置（仅零模型同步）');
    expect(html).toContain('同日自动任务、重试及手动操作共享额度');
    expect(html).toContain('电脑休眠或进程退出期间不运行');
    expect(state.request).not.toHaveBeenCalled();
    expect(html).not.toContain('provider-budget.json');
  });

  it('distinguishes effective historical admission limit from Today work slices and real failures', () => {
    const html = renderToStaticMarkup(<DailyExecutionSummary budget={{ day: '2026-09-11', configuredLimit: 100, attempted: 11, remaining: 89, materialExecution: { historicalDailyNewProjectLimit: 5, historicalLimitUnit: 'new_historical_projects_per_day', historicalLimitSource: 'explicit_settings_input', todayDailyProjectLimit: null, projectSliceLimit: 3, providerSliceRequestLimit: 6, failureRetryLimit: 2, serverProcessId: 99999 }, dailyStatus: { status: 'partial', modules: { historical_hot: { status: 'waiting', historicalAdmitted: 5, historicalNewAdmitted: 1, todayPending: 7, historicalPending: 20, visited: 3, providerRequests: 2, failedAttempts: 1, unclassifiedAttempts: 0, refreshed: 2, remaining: 27, checkedToday: 10, checkedHistorical: 25, waitReason: 'historical_daily_limit_reached' } } } }} />);
    expect(html).toContain('5 个新历史项目 / 自然日（显式配置值）');
    expect(html).toContain('不是 Today 与历史共享的尝试上限');
    expect(html).toContain('Today 无独立每日项目配额');
    expect(html).toContain('每工作片最多 3 个项目 / 6 次模型请求');
    expect(html).toContain('Today 资料待处理：7');
    expect(html).toContain('历史资料待处理：20');
    expect(html).toContain('真实失败尝试：1');
    expect(html).toContain('本轮模型请求：2');
    expect(html).toContain('新的历史项目等待下一自然日，Today 和已准入项目可继续续接');
    expect(html).not.toContain('99999');
    expect(state.request).not.toHaveBeenCalled();
  });
});
