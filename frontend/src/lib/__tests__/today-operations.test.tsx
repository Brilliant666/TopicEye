import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RardarTodayOperations, { TodayOperationResult } from '@/components/RardarTodayOperations';
import { todayOperationsApi, todayOperationLabel, type TodayOperation } from '@/lib/api/today-operations';

const state = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, loading: false, request: vi.fn() }));
vi.mock('@/providers/AuthProvider', () => ({ useAuthContext: () => ({ currentUser: state.user, authLoading: state.loading }) }));
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
  it('hides all administrator UI from anonymous/ordinary readers and never submits during render', () => {
    expect(renderToStaticMarkup(<RardarTodayOperations syncedAt={null} />)).toBe('');
    state.user = { id: 1, role: 'user' };
    expect(renderToStaticMarkup(<RardarTodayOperations syncedAt={null} />)).toBe('');
    state.user = { id: 1, role: 'admin' };
    const html = renderToStaticMarkup(<RardarTodayOperations syncedAt="2026-09-09T01:00:00Z" />);
    expect(html).toContain('查看榜单更新管理');
    expect(html).not.toContain('检查并同步榜单');
    expect(html).not.toContain('最近成功手动同步');
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

  it('does not present a legacy exact-window operation as the current dual-board check', () => {
    const old = operation('updated');
    expect(renderToStaticMarkup(<TodayOperationResult operation={old} context="dual_board" />)).toBe('');
    const current = { ...old, scope: 'dual_board' as const, status: 'partial' as const };
    const html = renderToStaticMarkup(<TodayOperationResult operation={current} context="dual_board" />);
    expect(html).toContain('部分来源已更新');
    expect(html).not.toContain('观察窗口');
    expect(html).not.toContain('2026/9/8');
    expect(state.request).not.toHaveBeenCalled();
  });

  it('does not mount the management status reader during ordinary board rendering', () => {
    state.user = { id: 1, role: 'admin' };
    const html = renderToStaticMarkup(<RardarTodayOperations context="dual_board" syncedAt="2026-09-10T01:00:00Z" checkedAt="2026-09-11T02:00:00Z" />);
    expect(html).toContain('查看榜单更新管理');
    expect(html).not.toContain('最近来源检查');
    expect(state.request).not.toHaveBeenCalled();
  });

  it('does not claim latest or published when an automatic sync owns the shared lock', () => {
    const html = renderToStaticMarkup(<TodayOperationResult operation={{ ...operation('skipped'), scope: 'dual_board', result: null }} context="dual_board" />);
    expect(html).toContain('已有同步正在执行，本次未重复启动');
    expect(html).not.toContain('已是最新');
    expect(html).not.toContain('已更新');
    expect(state.request).not.toHaveBeenCalled();
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

  it('separates successful source sync from a failed public Today publication', () => {
    const current: TodayOperation = { ...operation('partial'), scope: 'dual_board', result: {
      ...operation('partial').result!, sourceStatus: 'updated', readingStatus: 'failed', readingDisplay: 'previous',
      readingNote: '事实同步成功；公开成品发布失败，保留上次展示',
      sources: [{ source: 'github', status: 'healthy' }, { source: 'trendshift', status: 'healthy' }],
      readingPublication: { today: { status: 'failed', errorCode: 'internal-publication-failure' }, history: { status: 'published' } },
    } };
    const html = renderToStaticMarkup(<TodayOperationResult operation={current} context="dual_board" />);
    expect(html).toContain('<strong>公开成品发布失败</strong>');
    expect(html).toContain('事实同步成功；公开成品发布失败，保留上次展示');
    expect(html).not.toContain('部分来源暂不可用');
    expect(html).not.toContain('部分来源已更新');
    expect(html).not.toContain('internal-publication-failure');
    expect(state.request).not.toHaveBeenCalled();
  });

  it.each(['published', 'reused'] as const)('labels the actual Today public result %s instead of overall source status', readingStatus => {
    const current: TodayOperation = { ...operation('partial'), scope: 'dual_board', result: {
      ...operation('partial').result!, sourceStatus: 'updated', readingStatus, readingDisplay: 'current',
      readingPublication: { today: { status: readingStatus }, history: { status: 'failed' } },
    } };
    const html = renderToStaticMarkup(<TodayOperationResult operation={current} context="dual_board" />);
    expect(html).toContain(readingStatus === 'published' ? '<strong>公开成品已发布</strong>' : '<strong>公开成品未变，继续复用</strong>');
    expect(html).toContain('历史回顾公开成品发布失败，保留历史回顾上次展示');
    expect(html).not.toContain('<strong>公开成品发布失败</strong>');
    expect(html).not.toContain('部分来源暂不可用');
  });

  it('retains the real partial-source warning even when a usable public board publishes', () => {
    const current: TodayOperation = { ...operation('partial'), scope: 'dual_board', result: {
      ...operation('partial').result!, sourceStatus: 'partial', readingStatus: 'published', readingDisplay: 'current',
    } };
    const html = renderToStaticMarkup(<TodayOperationResult operation={current} context="dual_board" />);
    expect(html).toContain('公开成品已发布');
    expect(html).toContain('部分来源暂不可用');
  });
});
