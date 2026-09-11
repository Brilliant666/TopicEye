import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, expect, it, vi } from 'vitest';
import RardarProjectExplanation from '@/components/RardarProjectExplanation';
import { explainSharedProject, readSharedProjectInsight } from '@/lib/rardar-product';

afterEach(() => vi.unstubAllGlobals());

it('reads a saved insight using GET and only posts after the explicit action', async () => {
  const fetcher = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>().mockImplementation(async () =>
    new Response(JSON.stringify({ state: 'unprocessed', result: null }), { status: 200 }),
  );
  vi.stubGlobal('fetch', fetcher);
  await readSharedProjectInsight('stable-one', 'boards-one', 'trending');
  expect(fetcher.mock.calls[0][0]).toContain('/project-insights/stable-one?');
  expect(fetcher.mock.calls[0][1]).not.toHaveProperty('method', 'POST');
  await explainSharedProject('stable-one', 'history', 'historical_hot');
  expect(fetcher.mock.calls[1][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ generationId: 'history', context: 'historical_hot' }) });
});

it('renders the same opt-in control for a new stable project without numeric legacy ID', () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  for (const source of ['trending', 'historical_hot'] as const) {
    const html = renderToStaticMarkup(<RardarProjectExplanation stableId="stable-one" repository="real/project" generationId="boards-one" source={source} />);
    expect(html).toContain('生成 AI 深度解读');
  }
  expect(fetcher).not.toHaveBeenCalled();
});

it('reports login rather than silently submitting anonymously', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
  await expect(explainSharedProject('stable-one', 'one', 'trending')).rejects.toThrow('project_insight_login_required');
});
