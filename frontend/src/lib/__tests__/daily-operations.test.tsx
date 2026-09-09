import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarDailyOperations from '@/components/RardarDailyOperations';

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/lib/api/_core', () => ({ request: state.request }));

describe('Rardar daily admin controls', () => {
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
});
