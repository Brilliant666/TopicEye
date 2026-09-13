import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import RardarTrendingPage, { TrendingCard } from '@/components/RardarTrendingPage';
import { boardTime, loadTrending, projectLink, safeSourceUrl, type TrendingBoard, type TrendingCardNarrative, type TrendingProject } from '@/lib/rardar-trending';

vi.mock('@/components/RardarTodayOperations', () => ({ default: () => null }));
const project: TrendingProject = { projectId: 'new-repo--12345678901234567890', repository: 'new/repo', repositoryUrl: 'https://github.com/new/repo', githubRepositoryId: null, totalStars: null, description: null, dualListed: true, appearances: [{ source: 'github', rank: 1, sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null }, { source: 'trendshift', rank: 4, sourceDate: '2026-09-09', fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null }], materialState: 'unavailable', profile: null };
describe('refocused trending reading', () => {
  it.each([false, true])('preserves every rendered card field with the light narrative (historical=%s)', historical => {
    const displayCard: TrendingCardNarrative = {
      officialTaglineZh: '在实际资料中查找项目能力。', identitySummaryZh: '后备身份介绍',
      officialSummaryZh: '后备官方摘要', coreValueZh: '用可核对的资料帮助团队选型。',
      positioningZh: '后备定位', productFormsZh: ['命令行工具', '库'],
      officialNarrativeMode: 'official_translated', positioningSourceMode: 'official_translated',
    };
    const full = {
      ...project, materialState: 'complete' as const, language: 'TypeScript', topics: ['docs'], license: 'MIT',
      historicalContext: { kind: 'board' as const, source: 'github', dateKind: 'source' as const, date: '2026-09-09' },
      displayProfile: { ...displayCard, capabilities: [{ title: '仅详情能力', detail: '完整正文不随卡片传输。' }] } as TrendingProject['displayProfile'],
      displayEvidence: { evidenceIndex: { 'readme:1': { text: '仅详情原始证据' } } } as unknown as TrendingProject['displayEvidence'],
    };
    const light = { ...full, displayCard, displayProfile: undefined, displayEvidence: undefined };
    const render = (value: TrendingProject) => renderToStaticMarkup(<TrendingCard project={value} generationId="boards-saved" historical={historical} index={0} />);
    expect(render(light)).toBe(render(full));
    expect(render(light)).toContain('用可核对的资料帮助团队选型。');
    expect(render(light)).toContain(historical ? '历史记录' : '来源与更新时间');
    expect(render(light)).not.toContain('仅详情');
  });

  it('retains independent partial introduction and positioning fallbacks without a full profile', () => {
    const partial: TrendingProject = { ...project, materialState: 'partial', displayCard: null, profile: {
      summary: '独立保存的中文介绍。', positioning: '已有定位。', capabilities: [], generatedAt: null,
      sourceUrl: project.repositoryUrl, sourceLabel: '来源翻译',
    } };
    const html = renderToStaticMarkup(<TrendingCard project={partial} generationId="boards-saved" />);
    expect(html).toContain('独立保存的中文介绍。');
    expect(html).toContain('核心定位 · 已保存解读');
    expect(html).toContain('资料部分可用');
    expect(html).not.toContain('档案可用');
  });

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
    expect(html).toContain('来源报告历史上榜 123 次');
    expect(html).toContain('具体日期未知，不等于本地逐日记录');
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

const board: TrendingBoard = {
  schemaVersion: 1, generationId: 'boards-saved', publishedAt: '2026-09-13T01:00:00Z',
  checkedAt: '2026-09-13T01:00:01Z', sources: [], projects: [],
};

describe('daily focused lists', () => {
  it('renders the server-selected history batch in its saved order without loading a catalog', () => {
    const projects = [8, 3, 5].map(value => ({ ...project, projectId: `saved-${value}`, repository: `saved/repo-${value}` }));
    const html = renderToStaticMarkup(<RardarTrendingPage historical board={{ ...board, projects, dailyReview: {
      date: '2026-09-12', publishedAt: '2026-09-12T01:00:00Z', projectIds: projects.map(item => item.projectId),
      candidateCount: 132, limit: 8, lookbackDays: 7, relaxedRecentWindow: false, trigger: 'main',
    } }} />);
    expect(html).toContain('本期回顾 · 3 项');
    expect(html).toContain('回顾日期 2026-09-12');
    expect(html).not.toContain('2026/9/13');
    expect(html).not.toContain('132');
    expect(html).not.toContain('加载更多');
    expect(html).not.toContain('按累计 Star');
    expect(html).toContain('展示序号不是热度排名');
    expect(html.indexOf('saved/repo-8')).toBeLessThan(html.indexOf('saved/repo-3'));
    expect(html.indexOf('saved/repo-3')).toBeLessThan(html.indexOf('saved/repo-5'));
  });

  it('shows an unpublished review instead of pretending board publication is review publication', () => {
    const html = renderToStaticMarkup(<RardarTrendingPage historical board={{ ...board, state: 'pending_daily_review' }} />);
    expect(html).toContain('尚未发布每日回顾');
    expect(html).not.toContain('2026/9/13');
    expect(html).not.toContain('加载更多');
  });

  it('reports the configured growth cutoff and distinct raw, eligible and unknown counts', () => {
    const html = renderToStaticMarkup(<RardarTrendingPage board={{ ...board, projects: [project], rawProjectCount: 37, eligibleProjectCount: 1, unknownGrowthCount: 4, minimumDailyGrowth: 200 }} />);
    expect(html).toContain('展示来源报告日增长≥200的项目');
    expect(html).toContain('双榜项目优先采用GitHub Trending');
    expect(html).toContain('来源去重共 37 项 · 达标 1 项 · 主增长未知 4 项');
    expect(html).toContain('1 个达标项目');
  });

  it('distinguishes healthy below-cutoff emptiness from unavailable sources', () => {
    const healthySource = { source: 'github' as const, label: 'GitHub Trending', status: 'healthy' as const, sourceDate: '2026-09-12', fetchedAt: '2026-09-13T01:00:00Z', errorCode: null, count: 2 };
    const healthy = renderToStaticMarkup(<RardarTrendingPage board={{ ...board, sources: [healthySource] }} />);
    expect(healthy).toContain('本次有效来源中暂无日增长达到 200 的项目');
    const failed = renderToStaticMarkup(<RardarTrendingPage board={{ ...board, sources: [{ ...healthySource, status: 'failed' }] }} />);
    expect(failed).toContain('来源暂不可用，暂时没有可展示的达标项目');
  });

  it('does not report healthy empty results when no source facts exist', () => {
    const html = renderToStaticMarkup(<RardarTrendingPage board={{ ...board, sources: [], state: 'pending' }} />);
    expect(html).toContain('来源暂不可用，暂时没有可展示的达标项目');
    expect(html).not.toContain('本次有效来源中暂无');
  });

  it('keeps Today pagination limited to the already eligible server list', () => {
    const projects = Array.from({ length: 21 }, (_, index) => ({ ...project, projectId: `eligible-${index}`, repository: `eligible/repo-${index}` }));
    const html = renderToStaticMarkup(<RardarTrendingPage board={{ ...board, projects, rawProjectCount: 70, eligibleProjectCount: 21 }} />);
    expect((html.match(/data-project-id=/g) ?? [])).toHaveLength(20);
    expect(html).toContain('加载更多（剩余 1 项）');
    expect(html).not.toContain('eligible/repo-20');
  });
});
