import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarGrowthFacts from '@/components/RardarGrowthFacts';
import RardarTrendingPage, { TrendingCard } from '@/components/RardarTrendingPage';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { latestBoardAppearances, type BoardAppearance, type TrendingProject } from '@/lib/rardar-trending';

vi.mock('@/components/RardarTodayOperations', () => ({ default: () => null }));
const github: BoardAppearance = { source: 'github', rank: 2, sourceDate: '2026-09-10', fetchedAt: '2026-09-11T01:00:00Z', period: 'daily', reportedDelta: 627, reportedDeltaPeriod: 'GitHub reported stars today', sourceStatus: 'healthy', totalStars: 40030 };
const trendshift: BoardAppearance = { ...github, source: 'trendshift', rank: 8, reportedDelta: null, trendshiftStarsGained: 637, trendshiftMetricPeriod: 'past 24 hours', totalStars: 40109 };
const project: TrendingProject = { projectId: 'fixture-metrics', repository: 'fixture/metrics', repositoryUrl: 'https://github.com/fixture/metrics', githubRepositoryId: null, description: 'Fixture, not a product result.', totalStars: 40109, totalStarsSource: { source: 'trendshift', sourceDate: trendshift.sourceDate, fetchedAt: trendshift.fetchedAt, status: 'healthy' }, dualListed: true, appearances: [github, trendshift], primaryGrowth: { ...github, value: 627 }, materialState: 'unavailable', profile: null };

describe('single selected growth presentation', () => {
  it.each([github, trendshift])('shows selected $source without a second value', appearance => {
    const value = appearance.source === 'github' ? 627 : 637;
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, primaryGrowth: { ...appearance, value } }} />);
    expect(html).toContain(`data-growth-source="${appearance.source}"`);
    expect(html.match(/data-growth-source=/g)).toHaveLength(1);
    expect(html).toContain(`<strong>+${value}</strong>`);
    expect(html).not.toContain('精确 24');
    expect(html).toContain('40,109 累计 Star');
  });
  it('keeps GH zero and unknown distinct, independent of dual flag', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, dualListed: false, primaryGrowth: { ...github, value: 0 }, totalStars: null }} />);
    expect(html).toContain('<strong>+0</strong>');
    expect(html).toContain('累计 Star 未取得');
    const missing = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, primaryGrowth: null }} />);
    expect(missing).toContain('增长暂未取得');
    expect(missing).not.toContain('data-growth-source');
  });
  it('uses numeric value rather than source abbreviation', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, primaryGrowth: { ...trendshift, value: 1924, trendshiftStarsGainedLabel: '1.9k' } }} />);
    expect(html).toContain('<strong>+1,924</strong>');
    expect(html).not.toContain('1.9k');
  });
  it('keeps cache state visible without making current freshness claims', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, primaryGrowth: { ...github, value: 627, sourceStatus: 'stale' } }} />);
    expect(html).toContain('历史记录');
    expect(html).not.toContain('保留缓存');
    expect(html).toContain('历史 Star 增长');
    expect(html).not.toContain('今日新增');
  });
  it('retains absolute-time helper behavior for archival callers', () => {
    const old = { ...github, fetchedAt: '2026-09-11T08:59:59+08:00' };
    expect(latestBoardAppearances([old, trendshift, github])).toEqual([github, trendshift]);
    expect(latestBoardAppearances([github, trendshift, old])).toEqual([github, trendshift]);
  });
  it.each([false, true])('card and ordinary detail display the exact API metric (historical=%s)', historical => {
    for (const element of [<TrendingCard key="card" project={project} generationId="boards-fixture" historical={historical} />, <RardarProjectDetailPage key="detail" detail={{ ...project, generationId: 'boards-fixture' }} historical={historical} />]) {
      const html = renderToStaticMarkup(element);
      expect(html).toContain('<strong>+627</strong>');
      expect(html).not.toContain('<strong>+637</strong>');
      expect(html.match(/data-growth-source=/g)).toHaveLength(1);
    }
  });
  it('keeps full source provenance available separately and GET rendering has no fetch', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    try {
      const html = renderToStaticMarkup(<RardarTrendingPage board={{ schemaVersion: 1, generationId: 'boards-fixture', publishedAt: github.fetchedAt, checkedAt: github.fetchedAt, sources: [{ source: 'github', label: 'GitHub Trending', status: 'healthy', sourceDate: github.sourceDate, fetchedAt: github.fetchedAt, errorCode: null, count: 1 }], projects: [project] }} />);
      expect(html).toContain('来源与更新时间');
      expect(html).toContain('GitHub Trending #2');
      expect(html).toContain('Trendshift #8');
      expect(html).toContain('累计 Star 来源：Trendshift');
      expect(html).toContain('按来源报告的 Star 增长降序排列');
      expect(html).not.toContain('交错展示');
      expect(html).toContain('>看见热门项目，</span><span');
      expect(fetcher).not.toHaveBeenCalled();
    } finally { vi.unstubAllGlobals(); }
  });
});
