import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { newsOperationsApi, newsOperationLabel, type NewsOperation } from '@/lib/api/news-operations';
import RardarNewsOperations, { NewsOperationResult } from '@/components/RardarNewsOperations';

const state = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, request: vi.fn() }));
vi.mock('@/providers/AppProvider', () => ({ useAuthContext: () => ({ currentUser: state.user, authLoading: false }) }));
vi.mock('@/lib/api/_core', () => ({ request: state.request }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

beforeEach(() => { state.user = null; state.request.mockReset(); });

describe('News operator entry', () => {
  it('describes an all-paused refresh as skipped, retaining content rather than reporting a network failure', () => {
    const operation: NewsOperation = {
      id: 'paused', action: 'refresh', status: 'paused', startedAt: '2026-09-09T00:00:00Z', completedAt: '2026-09-09T00:00:01Z',
      errorCode: null, itemIds: [], requestLimit: 0,
      result: { providerCalls: 0, sources: [{ key: 'ars-technica', status: 'paused', created: 0, duplicates: 0, retained: 12 }] },
    };
    expect(newsOperationLabel(operation.status)).toBe('来源已暂停，未执行采集');
    const html = renderToStaticMarkup(<NewsOperationResult operation={operation} />);
    expect(html).toContain('已暂停 1 个来源');
    expect(html).toContain('已有内容保留');
    expect(html).toContain('来源失败 0 个');
    expect(state.request).not.toHaveBeenCalled();
  });

  it('shows login, hides controls for ordinary users, and offers two explicit admin actions', () => {
    const props = { source: null, topic: null, sort: 'balanced' as const, page: 1, itemCount: 18 };
    expect(renderToStaticMarkup(<RardarNewsOperations {...props} />)).toContain('管理员登录');
    state.user = { id: 1, role: 'user' };
    expect(renderToStaticMarkup(<RardarNewsOperations {...props} />)).toBe('');
    state.user = { id: 1, role: 'admin' };
    const html = renderToStaticMarkup(<RardarNewsOperations {...props} />);
    expect(html).toContain('更新资讯 · 不调用模型');
    expect(html).toContain('补充中文速读');
    expect(state.request).not.toHaveBeenCalled();
  });

  it('status reads are GET-only and explicit starts preserve retry identity without budget/path parameters', async () => {
    await newsOperationsApi.current();
    await newsOperationsApi.get('safe-id');
    expect(state.request.mock.calls[0]).toEqual(['/rardar/hotspot-news/operations', { cache: 'no-store' }]);
    expect(state.request.mock.calls[1]).toEqual(['/rardar/hotspot-news/operations/safe-id', { cache: 'no-store' }]);
    const input = { action: 'enhance' as const, requestId: 'unchanged-retry-id', sort: 'balanced' as const, page: 2 };
    await newsOperationsApi.start(input);
    await newsOperationsApi.start(input);
    expect(state.request.mock.calls[2]).toEqual(state.request.mock.calls[3]);
    expect(state.request.mock.calls[2][1]).toEqual({ method: 'POST', body: JSON.stringify(input) });
  });

  it('reports native, cached, title-only and failed content separately without inventing completed summaries', () => {
    const operation: NewsOperation = {
      id: 'a', action: 'enhance', status: 'degraded', startedAt: '2026-09-08T00:00:00Z', completedAt: null,
      errorCode: null, itemIds: [1, 2, 3, 4, 5], requestLimit: 12,
      result: { providerCalls: 2, considered: 4, enhanced: 1, cacheHits: 1, alreadyChinese: 1, failed: 1,
        items: [
          { contentId: 1, status: 'enhanced', materialKind: 'title_only', errorCode: null },
          { contentId: 2, status: 'cached', materialKind: 'feed_summary', errorCode: null },
          { contentId: 3, status: 'already_chinese', materialKind: null, errorCode: null },
          { contentId: 4, status: 'failed', materialKind: null, errorCode: 'fetch_failed' },
        ] },
    };
    const html = renderToStaticMarkup(<NewsOperationResult operation={operation} />);
    expect(html).toContain('未处理 1');
    expect(html).toContain('仅标题，未生成正文摘要');
    expect(html).toContain('已复用缓存');
    expect(html).toContain('处理失败');
    expect(html).toContain('本次模型请求 2 次');
    expect(newsOperationLabel('interrupted')).toBe('执行已中断');
    expect(newsOperationLabel('budget_exhausted')).toBe('额度已用尽');
  });
});
