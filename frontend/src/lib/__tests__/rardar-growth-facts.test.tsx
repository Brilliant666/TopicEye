import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarGrowthFacts from '@/components/RardarGrowthFacts';
import RardarTrendingPage, { TrendingCard } from '@/components/RardarTrendingPage';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { latestBoardAppearances, totalStarsProvenance, type BoardAppearance, type TrendingProject } from '@/lib/rardar-trending';

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
  it('history ignores legacy growth and uses only the saved total', () => {
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, primaryGrowth: { ...github, value: 627, sourceStatus: 'stale' } }} />);
    expect(html).toContain('<strong>40,109</strong>');
    expect(html).not.toContain('保留缓存');
    expect(html).not.toContain('增长');
    expect(html).not.toContain('今日新增');
  });
  it('retains absolute-time helper behavior for archival callers', () => {
    const old = { ...github, fetchedAt: '2026-09-11T08:59:59+08:00' };
    expect(latestBoardAppearances([old, trendshift, github])).toEqual([github, trendshift]);
    expect(latestBoardAppearances([github, trendshift, old])).toEqual([github, trendshift]);
  });
  it.each([0, null])('history preserves zero versus unknown total (%s)', totalStars => {
    const html = renderToStaticMarkup(<RardarGrowthFacts historical project={{ ...project, totalStars, primaryGrowth: null }} />);
    expect(html).toContain(totalStars === 0 ? '<strong>0</strong>' : '累计 Star 未取得');
    expect(html).not.toContain('增长');
  });
  it('keeps source data date separate from later local capture', () => {
    const text = totalStarsProvenance({ source: 'trendshift', sourceDate: '2026-09-01', fetchedAt: '2026-09-12T00:00:00Z', status: 'healthy', historicalSaved: true, timeKind: 'source_date' });
    expect(text).toContain('历史保存值 · 来源数据日期 2026-09-01');
    expect(text).toContain('本地采集');
    expect(text).not.toContain('实时');
    expect(totalStarsProvenance({ source: 'github_metadata', sourceDate: null, fetchedAt: github.fetchedAt, status: 'healthy', observedAt: github.fetchedAt, timeKind: 'observed' })).toContain('GitHub 仓库元数据 · 数据读取');
  });
  it('history legacy evidence does not leak a second total or any growth', () => {
    const old = { ...project, historicalRardarEvidence: [{ source: 'rardar_today' as const, sourceGeneration: 'old', servingGeneration: 'old-serving', rank: 3, windowStartedAt: '2026-08-01T00:00:00Z', windowEndedAt: '2026-08-02T00:00:00Z', observedStarDelta: 9876, totalStars: 99999 }] };
    for (const element of [<TrendingCard key="card" historical project={old} generationId="history" />, <RardarProjectDetailPage key="detail" historical detail={old} />]) {
      const html = renderToStaticMarkup(element);
      expect(html).not.toContain('9,876');
      expect(html).not.toContain('99,999');
      expect(html).not.toContain('主增长');
      expect(html).not.toContain('Star 增长');
      expect(html).toContain('累计 Star');
    }
  });
  it('renders valid partial introduction on both routes without inventing complete profile', () => {
    const partial = { ...project, materialState: 'partial' as const, profile: { summary: '用于组织小团队技术文档的工具。', positioning: null, capabilities: [], generatedAt: github.fetchedAt, sourceUrl: 'https://github.com/fixture/metrics#readme', sourceLabel: 'Rardar 中文简介' } };
    for (const historical of [false, true]) {
      for (const element of [<TrendingCard key="card" project={partial} generationId="boards-fixture" historical={historical} />, <RardarProjectDetailPage key="detail" detail={partial} historical={historical} />]) {
        const html = renderToStaticMarkup(element);
        expect(html).toContain(partial.profile.summary);
        expect(html).toContain('部分');
        expect(html).not.toContain('暂未取得可用的项目介绍');
      }
    }
  });
  it('only labels confirmed source failure, and does not cover existing text with errors', () => {
    for (const stage of ['source', 'profile', 'translation'] as const) {
      const item = { ...project, description: null, materialAttempt: { status: 'failed', stage } };
      const html = renderToStaticMarkup(<TrendingCard project={item} generationId="fixture" />);
      expect(html.includes('资料读取失败')).toBe(stage === 'source');
    }
    const html = renderToStaticMarkup(<TrendingCard project={{ ...project, materialAttempt: { status: 'failed', stage: 'source' } }} generationId="fixture" />);
    expect(html).toContain(project.description);
    expect(html).not.toContain('资料读取失败');
    expect(html).toContain('中文解读待补充');
  });
  it('partial introduction exposes source excerpt without inventing generation time', () => {
    const html = renderToStaticMarkup(<RardarProjectDetailPage historical detail={{ ...project, displayProfile: null, materialState: 'partial', profile: { summary: '用于团队协作的文档工具。', positioning: null, capabilities: [], generatedAt: null, savedAt: github.fetchedAt, sourceUrl: project.repositoryUrl, summaryEvidence: [{ ref: 'readme:1', text: 'A documentation tool for team collaboration.', url: `${project.repositoryUrl}#readme` }] }, material: { schemaVersion: 2, sourceKind: 'partial_introduction', sourceGeneration: 'fixture', sourceRevision: 'fixture', generatedAt: null, savedAt: github.fetchedAt }, totalStarsSource: { source: 'rardar_history', sourceDate: null, fetchedAt: null, status: 'saved', timeKind: 'unknown', historicalSaved: true } }} />);
    expect(html).toContain('中文简介依据');
    expect(html).toContain('A documentation tool for team collaboration.');
    expect(html).toContain(`${project.repositoryUrl}#readme`);
    expect(html).toContain('中文简介保存时间');
    expect(html).not.toContain('中文简介生成时间');
    expect(html).toContain('数据时间未知');
  });
  it.each([false, true])('card and detail preserve route-specific metrics (historical=%s)', historical => {
    for (const element of [<TrendingCard key="card" project={project} generationId="boards-fixture" historical={historical} />, <RardarProjectDetailPage key="detail" detail={{ ...project, generationId: 'boards-fixture' }} historical={historical} />]) {
      const html = renderToStaticMarkup(element);
      expect(html).toContain(historical ? '<strong>40,109</strong>' : '<strong>+627</strong>');
      expect(html).not.toContain('<strong>+637</strong>');
      expect(html.match(/data-growth-source=/g) || []).toHaveLength(historical ? 0 : 1);
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
