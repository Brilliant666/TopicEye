import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RardarTodayOperations, { TodayOperationResult } from '@/components/RardarTodayOperations';
import { todayOperationsApi, todayOperationLabel, type TodayOperation } from '@/lib/api/today-operations';

const state = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, loading: false, request: vi.fn() }));
vi.mock('@/providers/AppProvider', () => ({ useAuthContext: () => ({ currentUser: state.user, authLoading: state.loading }) }));
vi.mock('@/lib/api/_core', () => ({ request: state.request }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

beforeEach(() => { state.user = null; state.loading = false; state.request.mockReset(); });

function operation(status: TodayOperation['status']): TodayOperation {
  return {
    id: 'fixture-operation', status, startedAt: '2026-09-09T02:00:00Z', completedAt: status === 'running' ? null : '2026-09-09T02:00:02Z',
    errorCode: null, providerCalls: 0,
    result: { generationId: 'fixture-only', window: { startedAt: '2026-09-08T00:00:00Z', endedAt: '2026-09-09T00:00:00Z' }, syncedAt: '2026-09-09T01:00:00Z', changed: status === 'updated' },
  };
}

describe('Today daily operator entry', () => {
  it('offers admin login, hides ordinary-user actions, and never submits during render', () => {
    expect(renderToStaticMarkup(<RardarTodayOperations syncedAt={null} />)).toContain('管理员登录');
    state.user = { id: 1, role: 'user' };
    expect(renderToStaticMarkup(<RardarTodayOperations syncedAt={null} />)).toBe('');
    state.user = { id: 1, role: 'admin' };
    const html = renderToStaticMarkup(<RardarTodayOperations syncedAt="2026-09-09T01:00:00Z" />);
    expect(html).toContain('检查并同步榜单');
    expect(html).toContain('GitHub Trending 与 Trendshift 公开日榜 · 不调用模型');
    expect(html).toContain('最近成功同步');
    expect(html).toContain('最近检查');
    expect(html).toContain('disabled'); // Status must load before an action is allowed.
    expect(html).not.toContain('补齐');
    expect(state.request).not.toHaveBeenCalled();
    state.loading = true;
    expect(renderToStaticMarkup(<RardarTodayOperations syncedAt={null} />)).toBe('');
  });

  it('uses read-only status calls and explicit stable-identity POST with no configuration fields', async () => {
    await todayOperationsApi.current();
    await todayOperationsApi.get('safe/id');
    expect(state.request.mock.calls[0]).toEqual(['/rardar/today/operations', { cache: 'no-store' }]);
    expect(state.request.mock.calls[1]).toEqual(['/rardar/today/operations/safe%2Fid', { cache: 'no-store' }]);
    await todayOperationsApi.start('same-retry-id');
    await todayOperationsApi.start('same-retry-id');
    expect(state.request.mock.calls[2]).toEqual(state.request.mock.calls[3]);
    expect(state.request.mock.calls[2][1]).toEqual({ method: 'POST', body: JSON.stringify({ requestId: 'same-retry-id' }) });
  });

  it.each(['updated', 'unchanged', 'no_complete_board', 'failed', 'interrupted', 'not_configured'] as const)('shows honest terminal status %s without replacing the observed window with check time', (status) => {
    const html = renderToStaticMarkup(<TodayOperationResult operation={operation(status)} />);
    expect(html).toContain(todayOperationLabel(status));
    expect(html).toContain('2026/9/8');
    expect(html).toContain('08:00:00');
    expect(html).not.toContain('10:00:02');
    if (['failed', 'interrupted', 'not_configured'].includes(status)) expect(html).toContain('当前有效榜单保留');
    if (status === 'no_complete_board') expect(html).toContain('当前已保存内容保留');
    expect(state.request).not.toHaveBeenCalled();
  });

  it('keeps the old board readable while checking and does not expose internal error fields', () => {
    const running = operation('running');
    running.errorCode = 'fixture-internal-error';
    const html = renderToStaticMarkup(<TodayOperationResult operation={running} />);
    expect(html).toContain('正在检查 / 同步');
    expect(html).toContain('旧有效榜单会保留到验证通过');
    expect(html).not.toContain('fixture-internal-error');
  });
});
