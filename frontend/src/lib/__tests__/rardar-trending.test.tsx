import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { TrendingCard } from '@/components/RardarTrendingPage';
import { boardTime, loadTrending, projectLink, safeSourceUrl, type TrendingProject } from '@/lib/rardar-trending';

vi.mock('@/components/RardarTodayOperations', () => ({ default: () => null }));
const project: TrendingProject = { projectId: 'new-repo--12345678901234567890', repository: 'new/repo', repositoryUrl: 'https://github.com/new/repo', githubRepositoryId: null, totalStars: null, description: null, dualListed: true, appearances: [{ source: 'github', rank: 1, sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null }, { source: 'trendshift', rank: 4, sourceDate: '2026-09-09', fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null }], materialState: 'unavailable', profile: null };
describe('refocused trending reading', () => {
  it('renders identity and detail without numeric id, Profile, Star or local baseline', () => {
    const html = renderToStaticMarkup(<TrendingCard project={project} generationId="boards-test" />);
    expect(html).toContain('new/repo');
    expect(html).toContain('project/stable/new-repo');
    expect(html).toContain('双榜上榜');
    expect(html).toContain('GitHub Trending');
    expect(html).toContain('Trendshift');
    expect(html).not.toContain('精确 24');
    expect(html).not.toContain('0 累计');
  });
  it('keeps historical detail separate and never gives a current dual badge', () => {
    const html = renderToStaticMarkup(<TrendingCard historical project={project} generationId="boards-test" />);
    expect(html).toContain('history=1');
    expect(html).not.toContain('双榜上榜');
  });
  it('does not turn a historical source count into dated local appearances', () => {
    const html = renderToStaticMarkup(<TrendingCard historical project={{ ...project, appearances: [], historyAppearances: 0, firstSeenAt: '2026-09-10T00:00:00Z', historicalEvidence: [{ source: 'github', sourceUrl: 'https://trendshift.io/github-trending-repositories', reportedAppearanceCount: 123, sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z' }] }} generationId="history" />);
    expect(html).toContain('本地保存 0 次榜单记录');
    expect(html).toContain('历史上榜 123 次（来源报告，具体日期未知）');
    expect(html).toContain('最早采集');
    expect(html).not.toContain('最早上榜');
  });
  it('does not turn fetch time into a board date or allow unsafe source links', () => {
    expect(boardTime(null)).toBe('日期未知');
    expect(boardTime('2026-09-09')).toBe('2026-09-09');
    expect(safeSourceUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeSourceUrl('https://secret@example.com/')).toBeUndefined();
    expect(projectLink('new/repo', 'a&b')).toContain('new%2Frepo?generation=a%26b');
  });
  it('reading calls only the saved backend resource and safely handles failure', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: false });
    expect(await loadTrending('trending-today', fetcher)).toBeNull();
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
  });
});
