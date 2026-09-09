import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RardarDiscoverOperations, { DiscoverOperationResult, DiscoverPlanDetails } from '@/components/RardarDiscoverOperations';
import { discoverOperationsApi, type DiscoverPlan, type DiscoverOperation } from '@/lib/api/discover-operations';

const state = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, request: vi.fn() }));
vi.mock('@/providers/AppProvider', () => ({ useAuthContext: () => ({ currentUser: state.user, authLoading: false }) }));
vi.mock('@/lib/api/_core', () => ({ request: state.request }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
beforeEach(() => { state.user = null; state.request.mockReset(); });
const plan: DiscoverPlan = { id: 'fixture', candidates: [{ githubRepositoryId: 1, repository: 'fixture/one' }], candidateCount: 1, sourceObservationSetId: 'source-fixed', todayGenerationId: 'today-fixed', latestCaptureAt: null, requestLimit: 40, recallBatchId: 'batch-fixed' };

describe('Discover explicit operator entry', () => {
  it('keeps reads free and exposes an authenticated two-step entry, including empty initial data', () => {
    expect(renderToStaticMarkup(<RardarDiscoverOperations />)).toContain('管理员登录');
    state.user = { id: 1, role: 'user' };
    expect(renderToStaticMarkup(<RardarDiscoverOperations />)).toBe('');
    state.user = { id: 1, role: 'admin' };
    const html = renderToStaticMarkup(<RardarDiscoverOperations />);
    expect(html).toContain('生成下一批精选');
    expect(html).toContain('确认后才开始评估');
    expect(html).toContain('disabled');
    expect(state.request).not.toHaveBeenCalled();
  });
  it('sends only bounded server identities, never source, budget or candidate configuration', async () => {
    await discoverOperationsApi.current();
    await discoverOperationsApi.prepare('retry');
    await discoverOperationsApi.start('retry', 'plan');
    await discoverOperationsApi.start('retry', 'plan');
    expect(state.request.mock.calls[0][1]).toEqual({ cache: 'no-store' });
    expect(state.request.mock.calls[1][1]).toEqual({ method: 'POST', body: JSON.stringify({ requestId: 'retry' }) });
    expect(state.request.mock.calls[2][1]).toEqual({ method: 'POST', body: JSON.stringify({ requestId: 'retry', planId: 'plan' }) });
    expect(state.request.mock.calls[3]).toEqual(state.request.mock.calls[2]);
  });
  it('shows actual short batches and fixed provenance without requiring six projects', () => {
    const html = renderToStaticMarkup(<DiscoverPlanDetails plan={plan} />);
    expect(html).toContain('固定 1 项');
    expect(html).toContain('source-fixed');
    expect(html).toContain('today-fixed');
    expect(html).toContain('fixture/one');
  });
  it('distinguishes incomplete projects, no publication, and requests consumed', () => {
    const operation: DiscoverOperation = { id: 'op', status: 'completed', plan, providerCalls: 3, startedAt: '2026-09-09T00:00:00Z', completedAt: null, result: { processedCount: 1, publishedCount: 0, failedCount: 1, cacheHits: 0, generationId: null, installed: false, failures: [{ repository: 'fixture/one', reason: '资料获取失败' }] } };
    const html = renderToStaticMarkup(<DiscoverOperationResult operation={operation} />);
    expect(html).toContain('未完成 1 项');
    expect(html).toContain('3/40');
    expect(html).toContain('现有精选未替换');
    expect(html).toContain('资料获取失败');
    expect(state.request).not.toHaveBeenCalled();
  });
  it('shows safe diagnostic codes and a stopped run without exposing raw errors', () => {
    const operation: DiscoverOperation = { id: 'op', status: 'failed', plan, providerCalls: 2, startedAt: '2026-09-09T00:00:00Z', completedAt: null, errorCode: 'discover_operation_failed', result: { processedCount: 1, publishedCount: 0, failedCount: 1, cacheHits: 0, generationId: null, installed: false, failures: [], stopped: true, stopReason: 'rardar_llm_invalid_output' } };
    const html = renderToStaticMarkup(<DiscoverOperationResult operation={operation} />);
    expect(html).toContain('discover_operation_failed');
    expect(html).toContain('rardar_llm_invalid_output');
    expect(html).toContain('已停止新增请求');
    expect(html).toContain('安全结果保留');
    operation.errorCode = 'raw /secret?Authorization=example';
    operation.result!.stopReason = 'raw response body';
    const safeHtml = renderToStaticMarkup(<DiscoverOperationResult operation={operation} />);
    expect(safeHtml).not.toContain('Authorization');
    expect(safeHtml).not.toContain('raw response body');
  });
});
