import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Page from '@/app/project/stable/[projectId]/page';
import type { TrendingDetail } from '@/lib/rardar-trending';

const state = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not-found'); } }));
vi.mock('@/lib/product-profile', () => ({ isRardarProduct: () => true }));
vi.mock('@/lib/rardar-trending', () => ({ loadTrending: state.load }));
vi.mock('@/components/RardarProjectDetailPage', () => ({
  default: ({ detail, historical }: { detail: TrendingDetail; historical?: boolean }) => <div data-historical={String(historical)}>{detail.readingRevision || 'legacy-detail'}</div>,
}));
beforeEach(() => state.load.mockReset());

const projectId = `saved-project--${'a'.repeat(20)}`;
const generation = `boards-${'b'.repeat(64)}`;
const oldRevision = 'c'.repeat(64);
const newRevision = 'd'.repeat(64);
const detail = { projectId, generationId: generation };
const page = (query: Record<string, string | string[] | undefined>) => Page({
  params: Promise.resolve({ projectId }), searchParams: Promise.resolve(query),
});

describe('the real stable project route keeps the published reading revision', () => {
  it.each([false, true])('forwards both retained revisions without choosing latest (historical=%s)', async historical => {
    const query = historical ? { history: '1' } : { generation };
    for (const readingRevision of [oldRevision, newRevision]) {
      state.load.mockResolvedValueOnce({ ...detail, readingRevision });
      expect(renderToStaticMarkup(await page({ ...query, readingRevision }))).toContain(readingRevision);
      expect(state.load).toHaveBeenLastCalledWith(historical
        ? `historical-projects/${projectId}?readingRevision=${readingRevision}`
        : `trending-projects/${projectId}?generation=${generation}&readingRevision=${readingRevision}`);
    }
    expect(state.load).toHaveBeenCalledTimes(2);
  });

  it.each([false, true])('keeps old unversioned detail links compatible (historical=%s)', async historical => {
    state.load.mockResolvedValueOnce(detail);
    expect(renderToStaticMarkup(await page(historical ? { history: '1' } : { generation }))).toContain('legacy-detail');
    expect(state.load).toHaveBeenCalledWith(historical ? `historical-projects/${projectId}` : `trending-projects/${projectId}?generation=${generation}`);
  });

  it.each([{ readingRevision: '' }, { readingRevision: '../latest' }, { readingRevision: [oldRevision, newRevision] }])('rejects an explicit invalid revision instead of falling back: %j', async ({ readingRevision }) => {
    await expect(page({ generation, readingRevision })).rejects.toThrow('not-found');
    expect(state.load).not.toHaveBeenCalled();
  });

  it.each([null, detail, { ...detail, readingRevision: newRevision }])('fails closed when the requested old detail is unavailable or mismatched: %j', async value => {
    state.load.mockResolvedValueOnce(value);
    await expect(page({ generation, readingRevision: oldRevision })).rejects.toThrow('not-found');
    expect(state.load).toHaveBeenCalledOnce();
  });
});
