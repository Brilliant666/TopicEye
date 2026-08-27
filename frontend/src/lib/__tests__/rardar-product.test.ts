import { afterEach, describe, expect, it, vi } from 'vitest';

import { explainProject, findProjects, REUSE_TYPE_LABELS } from '@/lib/rardar-product';

afterEach(() => vi.unstubAllGlobals());

describe('Rardar product client', () => {
  it('posts only repository and generation for an explanation', async () => {
    const fetcher = vi.fn(async (_path: string, init: RequestInit) => {
      expect(JSON.parse(String(init.body))).toEqual({
        repository: 'owner/repository',
        generationId: 'generation-v1',
      });
      return new Response(JSON.stringify({ state: 'unavailable', errorCode: 'offline' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetcher);

    await explainProject('owner/repository', 'generation-v1');
    expect(fetcher).toHaveBeenCalledWith('/api/v1/rardar/projects/explain', expect.objectContaining({ method: 'POST' }));
  });

  it('supports both requirement-only and optional repository input', async () => {
    const payload = {
      quickCandidates: Array.from({ length: 5 }, (_, index) => ({ repository: `owner/repo-${index}` })),
      aiState: 'unavailable',
    };
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (_path: string, init: RequestInit) => {
      bodies.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify(payload), { status: 200 });
    }));

    await findProjects('我需要一个可复用的视频工具', null);
    await findProjects('这个项目有哪些模块可以复用', 'https://github.com/owner/repository');

    expect(bodies).toEqual([
      { requirement: '我需要一个可复用的视频工具', repositoryUrl: null },
      { requirement: '这个项目有哪些模块可以复用', repositoryUrl: 'https://github.com/owner/repository' },
    ]);
  });

  it('provides Chinese labels for all six approved reuse types', () => {
    expect(Object.keys(REUSE_TYPE_LABELS)).toEqual([
      'whole_product',
      'module_library',
      'provider_connector',
      'workflow',
      'reference_only',
      'not_recommended',
    ]);
    expect(Object.values(REUSE_TYPE_LABELS).every((label) => /[\u4e00-\u9fff]/.test(label))).toBe(true);
  });
});
