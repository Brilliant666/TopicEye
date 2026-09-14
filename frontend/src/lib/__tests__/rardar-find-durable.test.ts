import { afterEach, describe, expect, it, vi } from 'vitest';
import { executeFindRun, listFindRuns, readFindRun, submitFindRun, type FindRun } from '../rardar-product';
import RardarFindProjectPage, { findRunLabel } from '@/components/RardarFindProjectPage';

const identity = vi.hoisted(() => ({ id: 1 }));
vi.mock('@/providers/AppProvider', () => ({ useAuthContext: () => ({ currentUser: { id: identity.id }, authLoading: false }) }));

const run = (status: FindRun['status'] = 'created'): FindRun => ({ runId: 'stable-id', status, stage: status, request: { requirement: '测试私有需求', repositoryUrl: null }, result: null, createdAt: '2026-09-14T00:00:00Z', updatedAt: '2026-09-14T00:00:00Z', finishedAt: null, errorCode: null, requestLimit: 2, requestsUsed: 0, schemaVersion: 'rardar-find-run-v1' });
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
afterEach(() => vi.unstubAllGlobals());

describe('durable Find client protocol (mock transport, no Provider)', () => {
  it('keys the whole private form by application identity, resetting it on account change', () => {
    identity.id = 1;
    const first = RardarFindProjectPage({});
    identity.id = 2;
    const second = RardarFindProjectPage({});
    expect(first.type).toBe(second.type);
    expect(first.key).not.toBe(second.key);
  });
  it('receives a committed ID before execution and sends the same recovery key', async () => {
    const created = vi.fn();
    const fetcher = vi.fn().mockResolvedValueOnce(json(run())).mockImplementationOnce(async () => { expect(created).toHaveBeenCalledWith(run()); return json(run('completed')); });
    vi.stubGlobal('fetch', fetcher);
    expect((await submitFindRun(run().request, 'same-key', created)).status).toBe('completed');
    expect(fetcher.mock.calls[0][1].headers['Idempotency-Key']).toBe('same-key');
    expect(fetcher.mock.calls[1][0]).toMatch('/stable-id/execute');
  });
  it('lost create response only looks up the key without paid execution', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('connection lost')).mockResolvedValueOnce(json(run()));
    vi.stubGlobal('fetch', fetcher);
    expect((await submitFindRun(run().request, 'original-key', vi.fn())).status).toBe('created');
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/v1/rardar/find-runs', '/api/v1/rardar/find-runs/by-key/original-key']);
    expect(fetcher.mock.calls[1][1].method).toBeUndefined();
  });
  it('does not execute after the account session invalidates a pending create callback', async () => {
    let resolveCreate!: (value: Response) => void;
    const fetcher = vi.fn(() => new Promise<Response>((resolve) => { resolveCreate = resolve; }));
    vi.stubGlobal('fetch', fetcher);
    let currentSession = true;
    const writePrivateForm = vi.fn();
    const pending = submitFindRun(run().request, 'same-key', (value) => {
      if (!currentSession) return false;
      writePrivateForm(value.request);
      return true;
    });
    currentSession = false; // Logout/account switch before the response arrives.
    resolveCreate(json(run()));
    await pending;
    expect(writePrivateForm).not.toHaveBeenCalled();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('lost execute response recovers the same result with GET, never retries POST', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('connection lost')).mockResolvedValueOnce(json(run('uncertain')));
    vi.stubGlobal('fetch', fetcher);
    expect((await executeFindRun('stable-id')).status).toBe('uncertain');
    expect(fetcher.mock.calls.map(([, options]) => options.method)).toEqual(['POST', undefined]);
  });
  it('new session and recent reads use server GET only, private no-store', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json(run('completed'))).mockResolvedValueOnce(json({ runs: [] })).mockResolvedValueOnce(json(run('completed')));
    vi.stubGlobal('fetch', fetcher);
    await readFindRun('stable-id'); await listFindRuns(); await readFindRun('stable-id');
    for (const [, options] of fetcher.mock.calls) { expect(options.method).toBeUndefined(); expect(options.cache).toBe('no-store'); expect(options.credentials).toBe('same-origin'); }
  });
  it('read authorization failure is not retried or replaced with browser history', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 401 })); vi.stubGlobal('fetch', fetcher);
    await expect(readFindRun('private-id')).rejects.toThrow('请先登录'); expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it.each(['partial', 'failed', 'budget_stopped', 'interrupted', 'uncertain'] as const)('does not label %s as complete success', (status) => {
    expect(findRunLabel(status)).not.toContain('完整结果已保存');
    expect(findRunLabel(status)).toBeTruthy();
  });
});
