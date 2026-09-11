import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarGrowthFacts from '@/components/RardarGrowthFacts';
import RardarTrendingPage, { TrendingCard } from '@/components/RardarTrendingPage';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { boardTime, latestBoardAppearances, type BoardAppearance, type TrendingProject } from '@/lib/rardar-trending';

vi.mock('@/components/RardarTodayOperations', () => ({ default: () => null }));
const github: BoardAppearance = { source: 'github', rank: 2, sourceDate: '2026-09-10', fetchedAt: '2026-09-11T01:00:00Z', period: 'daily', reportedDelta: 627, reportedDeltaPeriod: 'GitHub reported stars today', sourceStatus: 'healthy', totalStars: 40030 };
const trendshift: BoardAppearance = { source: 'trendshift', rank: 8, sourceDate: '2026-09-10', fetchedAt: '2026-09-11T01:05:00Z', period: 'daily', reportedDelta: null, trendshiftStarsGained: 637, trendshiftStarsGainedLabel: 'Stars gained', trendshiftMetricPeriod: 'past 24 hours', sourceStatus: 'healthy', totalStars: 40109 };
const project: TrendingProject = { projectId: 'fixture-metrics', repository: 'fixture/metrics', repositoryUrl: 'https://github.com/fixture/metrics', githubRepositoryId: null, description: 'A fixture for source metrics, not a product sample.', totalStars: 40109, totalStarsSource: { source: 'trendshift', sourceDate: trendshift.sourceDate, fetchedAt: trendshift.fetchedAt, status: 'healthy' }, dualListed: true, appearances: [github, trendshift], materialState: 'unavailable', profile: null };

describe('source-specific growth presentation', () => {
  it.each([github, trendshift])('shows the real single-source value for $source without requiring another source', appearance => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, appearances: [appearance], dualListed: false }} />);
    expect(html).toContain(`data-growth-source="${appearance.source}"`);
    expect(html.match(/data-growth-source=/g)).toHaveLength(1);
    expect(html).toContain(`<strong>+${appearance.source === 'github' ? 627 : 637}</strong>`);
    expect(html).not.toContain('精确 24');
  });

  it('keeps both growth values primary, total secondary, and each source time attributable', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={project} />);
    expect(html).toContain('<strong>+627</strong>');
    expect(html).toContain('<strong>+637</strong>');
    expect(html).toContain('来源报告 Star 增长 · past 24 hours');
    expect(html).toContain('来源报告 stars today');
    expect(html).toContain('榜单日期 2026-09-10');
    expect(html).toContain(boardTime(github.fetchedAt));
    expect(html).toContain(boardTime(trendshift.fetchedAt));
    expect(html).toContain('40,109 累计 Star');
    expect(html).toContain('累计来源 Trendshift');
    expect(html).not.toContain('<strong>40,109');
    expect(html).not.toContain('1,264');
    expect(html).not.toContain('632');
    expect(html).not.toContain('精确');
  });

  it('keeps measured zero distinct from a missing value and never uses fetchedAt as source date', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, appearances: [{ ...github, reportedDelta: 0, sourceDate: null }, { ...trendshift, trendshiftStarsGained: null }], totalStars: null, totalStarsSource: null }} />);
    expect(html).toContain('<strong>+0</strong>');
    expect(html).toContain('榜单日期 日期未知');
    expect(html).toContain('Trendshift：增长未取得');
    expect(html.match(/data-growth-source=/g)).toHaveLength(1);
    expect(html).toContain('累计 Star 未取得');
    expect(html).not.toContain('0 累计');
  });

  it('shows the source integer without replacing it with the separately captured abbreviated label', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts project={{ ...project, appearances: [{ ...trendshift, trendshiftStarsGained: 1924, trendshiftStarsGainedLabel: '1.9k', trendshiftMetricPeriod: 'Trendshift daily (source-defined window)' }] }} />);
    expect(html).toContain('<strong>+1,924</strong>');
    expect(html).not.toContain('<strong>+1.9k</strong>');
    expect(html).toContain('title="来源页面原标签：1.9k"');
    expect(html).toContain('来源日榜周期，具体起止未提供');
  });

  it('labels stale and failed cached metrics as historical rather than current healthy results', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, appearances: [{ ...github, sourceStatus: 'stale' }, { ...trendshift, sourceStatus: 'failed' }], totalStarsSource: { ...project.totalStarsSource!, status: 'stale' } }} />);
    expect(html).toContain('历史 · GitHub Trending · 历史缓存');
    expect(html).toContain('历史 · Trendshift · 来源失败 · 保留缓存');
    expect(html).toContain('历史榜日期 2026-09-10');
    expect(html).toContain('累计来源 Trendshift · 历史缓存');
    expect(html).not.toContain('今日新增');
  });

  it('chooses each historical source latest capture by absolute time, independent of array order', () => {
    const oldGithub = { ...github, reportedDelta: 13, fetchedAt: '2026-09-11T08:59:59+08:00' };
    const rows = [oldGithub, trendshift, github];
    const original = [...rows];
    expect(latestBoardAppearances(rows)).toEqual([github, trendshift]);
    expect(latestBoardAppearances([...rows].reverse())).toEqual([github, trendshift]);
    expect(rows).toEqual(original);
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, appearances: rows }} />);
    expect(html).not.toContain('<strong>+13</strong>');
    expect(html.match(/data-growth-source=/g)).toHaveLength(2);
  });

  it('retains the true old Rardar window instead of inventing a source growth period', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, appearances: [], totalStarsSource: null, historicalRardarEvidence: [{ source: 'rardar_today', sourceGeneration: 'old-facts', servingGeneration: 'old-serving', rank: 1, windowStartedAt: '2026-08-28T00:00:00Z', windowEndedAt: '2026-08-29T00:00:00Z', observedStarDelta: 5246, totalStars: 40000 }] }} />);
    expect(html).toContain('Rardar 历史观测');
    expect(html).toContain('<strong>+5,246</strong>');
    expect(html).toContain(boardTime('2026-08-28T00:00:00Z'));
    expect(html).toContain('历史窗口结束时的保存值');
    expect(html).not.toContain('GitHub Trending');
  });

  it.each([false, true])('uses the identical metric component in card and detail (history=%s)', historical => {
    for (const element of [<TrendingCard key="card" project={project} generationId="boards-fixture" historical={historical} />, <RardarProjectDetailPage key="detail" detail={{ ...project, generationId: 'boards-fixture' }} historical={historical} />]) {
      const html = renderToStaticMarkup(element);
      expect(html).toContain('<strong>+627</strong>');
      expect(html).toContain('<strong>+637</strong>');
      expect(html).toContain('累计来源 Trendshift');
      expect(html).not.toContain('精确 24');
    }
  });

  it('exposes concise source freshness above the list and phrase-safe heading segments without a request', () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    try {
      const html = renderToStaticMarkup(<RardarTrendingPage board={{ schemaVersion: 1, generationId: 'boards-fixture', publishedAt: github.fetchedAt, checkedAt: trendshift.fetchedAt, sources: [{ source: 'github', label: 'GitHub Trending', status: 'healthy', sourceDate: github.sourceDate, fetchedAt: github.fetchedAt, errorCode: null, count: 1 }, { source: 'trendshift', label: 'Trendshift', status: 'stale', sourceDate: trendshift.sourceDate, fetchedAt: trendshift.fetchedAt, errorCode: null, count: 1 }], projects: [project] }} />);
      expect(html).toContain('aria-label="两源读取状态"');
      expect(html.indexOf('两源读取状态')).toBeLessThan(html.indexOf('aria-label="双榜今日热榜"'));
      expect(html).toContain('Trendshift：历史缓存');
      expect(html).toContain('>看见热门项目，</span><span');
      expect(html).toContain('>读懂它的价值</span>');
      expect(fetcher).not.toHaveBeenCalled();
    } finally { vi.unstubAllGlobals(); }
  });
});
