import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RardarDiscoverPage, { filterDiscoverStages } from '@/components/RardarDiscoverPage';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import {
  loadDiscover,
  loadDiscoverProjectDetail,
  parseDiscoverProjectDetail,
  parseDiscoverResponse,
  type DiscoverCard,
  type DiscoverProjectDetail,
  type DiscoverResponse,
} from '@/lib/rardar-discover';

const capability = {
  title: '证据驱动能力',
  detail: '根据仓库描述与官方文档整理可验证的核心功能。',
  shortDetail: '整理可验证功能',
  evidenceRefs: ['readme:section:1'],
  sourceMode: 'rardar_derived' as const,
};

const card: DiscoverCard = {
  githubRepositoryId: 42,
  repository: 'fixture-lab/realtime-project',
  url: 'https://github.com/fixture-lab/realtime-project',
  stage: 'just_discovered',
  firstSeenAt: '2026-08-30T00:00:00Z',
  lastObservedAt: '2026-08-30T04:00:00Z',
  observedWindowStart: '2026-08-30T00:00:00Z',
  observedWindowEnd: '2026-08-30T04:00:00Z',
  observedWindowHours: 4,
  observedStarDelta: 87,
  totalStars: 1287,
  captureCount: 3,
  consecutiveCaptureCount: 3,
  language: 'TypeScript',
  topics: ['developer-tools', 'automation'],
  license: 'MIT',
  isFork: false,
  isArchived: false,
  isDisabled: false,
  latestPushAt: '2026-08-30T03:00:00Z',
  sourceCaptureIds: ['capture-1', 'capture-2', 'capture-3'],
  sourceEvidenceDigest: 'a'.repeat(64),
  relativeGrowthPercent: 7.25,
  positiveIntervalCount: 2,
  consecutivePositiveIntervalCount: 2,
  latestIntervalDelta: 20,
  publishReasonCodes: ['first_seen_recently'],
  signalFacts: ['first_seen_recently'],
  identitySummaryZh: '一个帮助开发者验证近实时项目变化的开源工具。',
  positioningZh: '通过连续观察与审计证据呈现项目的真实增长变化。',
  capabilities: [capability],
  sourceMode: 'rardar_derived',
  qualityState: 'partial',
  category: 'dev-tools',
  categorySourceMode: 'canonical_profile',
  categoryEvidenceRefs: ['readme:section:1'],
};

const board: DiscoverResponse = {
  status: 'ready',
  generation: 'discover-generation-1',
  generatedAt: '2026-08-30T04:10:00Z',
  latestCaptureId: 'trending-v1-20260830T040000Z',
  latestCaptureAt: '2026-08-30T04:05:00Z',
  nextExpectedAt: '2026-08-30T06:00:00Z',
  freshnessState: 'fresh',
  updateCadenceMinutes: 120,
  stageCounts: { justDiscovered: 1, outsideTodayMomentum: 0, rising: 0, nearValidation: 0 },
  stages: { justDiscovered: [card], outsideTodayMomentum: [], rising: [], nearValidation: [] },
  coverage: {
    state: 'degraded',
    querySuccessCount: 8,
    queryFailureCount: 1,
    metadataFailureCount: 2,
    sourceCaptureCount: 3,
    candidateCount: 17,
    publishedCount: 1,
    conflictCount: 1,
    excludedExactCount: 4,
  },
  conflicts: { count: 1, reasons: { star_count_decreased: 1 } },
  todayExplosionGenerationId: 'today-generation-1',
  sourceWindowStart: '2026-08-29T02:00:00Z',
  sourceWindowEnd: '2026-08-30T04:00:00Z',
  sourceCaptureCount: 3,
  profileSummary: {
    selectedCount: 1,
    identityComplete: 1,
    positioningComplete: 1,
    capabilitiesComplete: 1,
    categoryComplete: 1,
    officialZh: 0,
    officialTranslated: 0,
    rardarDerived: 1,
    githubRequests: 0,
    readmeCacheHits: 1,
    translationCalls: 0,
    translationCacheHits: 1,
  },
  sourceSchemaVersion: 2,
  sourcePolicyVersion: 'trending-discover-v2',
  suppressionSummary: {
    candidateCount: 17,
    stageEligibleCount: 3,
    publishedCount: 1,
    suppressedWeakSignalCount: 2,
    suppressedExactCount: 4,
    conflictCount: 1,
    reasons: {
      weak_absolute_growth: 2,
      weak_relative_growth: 1,
      no_continuous_growth: 1,
      already_in_today: 4,
      identity_conflict: 0,
      negative_growth: 1,
      disabled: 0,
      metadata_incomplete: 2,
    },
  },
  code: null,
};

const profile = {
  profileSchemaVersion: 'rardar-project-profile-v7',
  promptVersion: 'rardar-project-profile-zh-v15',
  githubRepositoryId: 42,
  repository: card.repository,
  htmlUrl: card.url,
  generationId: board.generation,
  profileState: 'complete',
  officialSummaryZh: card.identitySummaryZh,
  sourceLabel: 'Rardar 整理',
  sourceLanguage: 'zh',
  capabilityBulletsZh: [capability.detail],
  capabilities: [capability],
  productFormsZh: ['开发工具'],
  supportedEnvironmentsZh: ['本地开发环境'],
  primaryUseCasesZh: ['验证项目增长变化'],
  deliveryFormsZh: ['源代码'],
  claimEvidenceRefs: {
    [card.identitySummaryZh]: ['description'],
    [card.positioningZh]: ['readme:section:1'],
  },
  readmePath: 'README.md',
  readmeBlobSha: 'b'.repeat(40),
  selectedSections: [],
  originalExcerpts: ['Continuous observations expose verified project changes.'],
  startHere: [],
  evidenceDigest: 'c'.repeat(64),
  generatedAt: '2026-08-30T04:10:00Z',
  translationState: 'not_needed',
  identitySummaryZh: card.identitySummaryZh,
  coreValueZh: null,
  coreValueEvidenceRefs: [],
  keyDifferentiators: [],
  qualityState: 'partial',
  qualityIssues: ['assessment_missing'],
  officialTaglineZh: card.identitySummaryZh,
  officialTaglineEvidenceRefs: ['description'],
  officialPositioningZh: card.positioningZh,
  officialPositioningEvidenceRefs: ['readme:section:1'],
  positioningZh: card.positioningZh,
  positioningSourceMode: 'rardar_derived',
  positioningEvidenceRefs: ['readme:section:1'],
  positioningIncludedRoles: ['identity', 'core_mechanism'],
  positioningExcludedClauses: [],
  officialHighlights: [],
  officialNarrativeMode: 'rardar_derived',
  officialNarrativeIssues: ['source_structure_weak'],
  officialNarrativePromptVersion: 'rardar-official-narrative-zh-v2',
  rardarAssessmentZh: null,
  rardarAssessmentEvidenceRefs: [],
  rardarDifferentiators: [],
  rardarAssessmentPromptVersion: 'rardar-assessment-zh-v12',
} as const;

const detail = {
  schemaVersion: 2,
  servingGenerationId: 'discover-generation-1--serving',
  discoverGenerationId: board.generation,
  facts: card,
  profile,
  evidence: {
    schemaVersion: 1,
    githubRepositoryId: 42,
    repository: card.repository,
    generationId: board.generation,
    readmePath: 'README.md',
    readmeBlobSha: 'b'.repeat(40),
    sourceLanguage: 'zh',
    selectedSections: [],
    originalExcerpts: [],
    topLevelTree: [],
    evidenceIndex: {
      description: card.identitySummaryZh,
      'readme:section:1': card.positioningZh,
    },
    pathRefs: {},
    digest: 'c'.repeat(64),
  },
  coverage: board.coverage,
  conflictCount: 1,
  category: card.category,
  categorySourceMode: card.categorySourceMode,
  categoryEvidenceRefs: card.categoryEvidenceRefs,
  nextExpectedAt: board.nextExpectedAt,
  nextTodaySettlementAt: '2026-08-31T00:00:00Z',
  todayStatus: 'not_in_source_today',
  todayReason: 'new_candidate',
} as unknown as DiscoverProjectDetail;

const outsideCard: DiscoverCard = {
  ...card,
  githubRepositoryId: 86,
  repository: 'fixture-lab/outside-momentum',
  url: 'https://github.com/fixture-lab/outside-momentum',
  stage: 'outside_today_momentum',
  observedWindowHours: 24,
  observedStarDelta: 38,
  totalStars: 2038,
  captureCount: 13,
  consecutiveCaptureCount: 13,
  positiveIntervalCount: 5,
  consecutivePositiveIntervalCount: 2,
  latestIntervalDelta: 7,
  publishReasonCodes: [
    'outside_today_top20',
    'exact_rank_available',
    'recent_absolute_growth',
    'continuous_recent_growth',
    'recent_acceleration',
  ],
  signalFacts: [
    'outside_today_top20',
    'exact_rank_available',
    'recent_absolute_growth',
    'continuous_recent_growth',
    'recent_acceleration',
  ],
  eligibilityClass: 'exact_outside_published',
  todayExactRank: 86,
  todayExact24hDelta: 38,
  recentWindowHours: 4,
  recentObservedStarDelta: 12,
  priorComparableWindowDelta: 3,
  accelerationDelta: 9,
  recentRelativeGrowthPercent: 0.59,
  identitySummaryZh: '一个提供可验证短窗口变化的榜外开源项目。',
  positioningZh: '通过连续 Observation 呈现进入 Today Top 20 之外的新异动。',
};

const v3PreExactCard: DiscoverCard = {
  ...card,
  eligibilityClass: 'pre_exact',
  todayExactRank: null,
  todayExact24hDelta: null,
  recentWindowHours: 4,
  recentObservedStarDelta: 87,
  priorComparableWindowDelta: null,
  accelerationDelta: null,
  recentRelativeGrowthPercent: 7.25,
};

const v3Board: DiscoverResponse = {
  ...board,
  generation: 'discover-generation-v3',
  stageCounts: { justDiscovered: 1, outsideTodayMomentum: 1, rising: 0, nearValidation: 0 },
  stages: {
    justDiscovered: [v3PreExactCard],
    outsideTodayMomentum: [outsideCard],
    rising: [],
    nearValidation: [],
  },
  coverage: {
    ...board.coverage!,
    candidateCount: 31,
    publishedCount: 2,
    conflictCount: 1,
    excludedExactCount: null,
    todayExactCount: 27,
    todayPublishedCount: 20,
    excludedPublishedCount: 20,
    exactOutsidePublishedEvaluatedCount: 7,
    preExactEvaluatedCount: 3,
    invalidCount: 1,
  },
  profileSummary: {
    ...board.profileSummary!,
    selectedCount: 2,
    identityComplete: 2,
    positioningComplete: 2,
    capabilitiesComplete: 2,
    categoryComplete: 2,
    rardarDerived: 2,
  },
  sourceSchemaVersion: 3,
  sourcePolicyVersion: 'trending-discover-v3',
  todayPublishedTopCount: 20,
  suppressionSummary: {
    candidateCount: 31,
    publishedCount: 2,
    suppressedSignalCount: 8,
    excludedPublishedCount: 20,
    conflictCount: 1,
    reasons: {
      today_published: 20,
      weak_recent_absolute_growth: 3,
      weak_recent_relative_growth: 2,
      no_recent_continuous_growth: 1,
      no_recent_acceleration: 2,
      weak_pre_exact_growth: 1,
      already_exact_without_momentum: 6,
      identity_conflict: 1,
      negative_growth: 0,
      disabled: 0,
      metadata_incomplete: 0,
    },
  },
  eligibilitySummary: {
    observationCandidates: 31,
    todayExactFacts: 27,
    todayPublished: 20,
    excludedPublished: 20,
    exactOutsidePublishedEvaluated: 7,
    preExactEvaluated: 3,
    invalid: 1,
    published: 2,
    suppressed: 8,
  },
};

const v3Detail: DiscoverProjectDetail = {
  ...detail,
  schemaVersion: 3,
  discoverGenerationId: v3Board.generation!,
  facts: outsideCard,
  profile: {
    ...detail.profile,
    githubRepositoryId: outsideCard.githubRepositoryId,
    repository: outsideCard.repository,
    htmlUrl: outsideCard.url,
    generationId: v3Board.generation!,
  },
  evidence: {
    ...detail.evidence,
    githubRepositoryId: outsideCard.githubRepositoryId,
    repository: outsideCard.repository,
    generationId: v3Board.generation!,
  },
  coverage: v3Board.coverage!,
  todayStatus: 'outside_today_top20',
  todayReason: 'outside_today_top20_with_momentum',
  todayPublishedTopCount: 20,
};

describe('Rardar near-real-time Discover', () => {
  it('renders four honest stages, actual windows, coverage, and internal detail navigation', () => {
    const html = renderToStaticMarkup(<RardarDiscoverPage result={{ kind: 'published', board }} />);

    expect(html).toContain('发现此刻正在形成的真实信号');
    expect(html).toContain('每 2 小时');
    expect(html.indexOf('刚刚发现')).toBeLessThan(html.indexOf('榜外异动'));
    expect(html.indexOf('榜外异动')).toBeLessThan(html.indexOf('持续升温'));
    expect(html.indexOf('持续升温')).toBeLessThan(html.indexOf('待日榜验证'));
    expect(html).toContain('+87');
    expect(html).toContain('/ 实际 4 小时');
    expect(html).toContain('本次已验证 Observation 中没有符合该阶段信号门禁的项目');
    expect(html).toContain('/project/github/42?discoverGeneration=discover-generation-1');
    expect(html).toContain('role="link"');
    expect(html).toContain('tabindex="0"');
    expect(html).toContain('开发工具');
    expect(html).toContain('弱信号抑制');
    expect(html).not.toContain('查看项目详情');
    expect(html).toContain('Metadata failure 2');
    expect(html).toContain('不代表 GitHub 全站绝对完整扫描');
    expect(html).not.toContain('预计 24h');
    expect(html).not.toContain('全网排名');
  });

  it('filters categories without reordering the producer-owned stage arrays', () => {
    const first = { ...card, githubRepositoryId: 43, repository: 'fixture-lab/first' };
    const second = { ...card, githubRepositoryId: 44, repository: 'fixture-lab/second', category: 'ai-agent' as const };
    const third = { ...card, githubRepositoryId: 45, repository: 'fixture-lab/third' };
    const filtered = filterDiscoverStages({
      justDiscovered: [first, second, third],
      outsideTodayMomentum: [],
      rising: [],
      nearValidation: [],
    }, 'dev-tools');
    expect(filtered.justDiscovered.map((item) => item.githubRepositoryId)).toEqual([43, 45]);
  });

  it('renders stale and fail-closed states without demo fallback', () => {
    const stale = renderToStaticMarkup(
      <RardarDiscoverPage result={{ kind: 'published', board: { ...board, status: 'stale', freshnessState: 'stale' } }} />,
    );
    const invalid = renderToStaticMarkup(
      <RardarDiscoverPage result={{ kind: 'invalid', code: 'rardar_discover_invalid' }} />,
    );
    expect(stale).toContain('数据已延迟');
    expect(invalid).toContain('完整性验证失败');
    expect(invalid).toContain('没有回退到 Demo');
  });

  it('validates stage identity and maps ready, not-configured, and invalid API states', async () => {
    expect(parseDiscoverResponse(board).generation).toBe('discover-generation-1');
    expect(() => parseDiscoverResponse({
      ...board,
      stages: { ...board.stages, rising: [{ ...card, stage: 'rising' }] },
    })).toThrow('rardar_discover_response_invalid');

    const loaded = await loadDiscover(async () => new Response(JSON.stringify(board), { status: 200 }), 'http://backend.test');
    const notConfigured = await loadDiscover(async () => new Response(JSON.stringify({
      ...board,
      status: 'not_configured',
      generation: null,
      freshnessState: 'unavailable',
      coverage: null,
      stages: { justDiscovered: [], outsideTodayMomentum: [], rising: [], nearValidation: [] },
      code: 'rardar_discover_not_configured',
    }), { status: 503 }), 'http://backend.test');
    const invalid = await loadDiscover(async () => {
      throw new Error('offline');
    }, 'http://backend.test');
    expect(loaded.kind).toBe('published');
    expect(notConfigured).toEqual({ kind: 'not_configured', code: 'rardar_discover_not_configured' });
    expect(invalid).toEqual({ kind: 'invalid', code: 'rardar_discover_unavailable' });
  });

  it('renders and validates audited v3 outside-Today momentum without prediction language', () => {
    const parsed = parseDiscoverResponse(v3Board);
    const html = renderToStaticMarkup(
      <RardarDiscoverPage result={{ kind: 'published', board: parsed }} />,
    );

    expect(parsed.todayPublishedTopCount).toBe(20);
    expect(parsed.eligibilitySummary?.exactOutsidePublishedEvaluated).toBe(7);
    expect(html).toContain('榜外异动');
    expect(html).toContain('最近实际 4 小时');
    expect(html).toContain('+12');
    expect(html).toContain('前一相同窗口');
    expect(html).toContain('+3 Star');
    expect(html).toContain('加速变化');
    expect(html).toContain('+9 Star');
    expect(html).toContain('Today exact');
    expect(html).toContain('#86 · 24h +38');
    expect(html).toContain('榜外已评估 7');
    expect(html).not.toContain('预测进入 Today');
    expect(html).not.toContain('预计 24h');

    expect(() => parseDiscoverResponse({
      ...v3Board,
      todayPublishedTopCount: 19,
    })).toThrow('rardar_discover_response_invalid');
    expect(() => parseDiscoverResponse({
      ...v3Board,
      stages: {
        ...v3Board.stages,
        outsideTodayMomentum: [{ ...outsideCard, accelerationDelta: null }],
      },
    })).toThrow('rardar_discover_response_invalid');
    expect(() => parseDiscoverResponse({
      ...v3Board,
      eligibilitySummary: { ...v3Board.eligibilitySummary!, published: 3 },
    })).toThrow('rardar_discover_response_invalid');
  });

  it('binds Discover detail to its own generation and reuses AI and Find Project actions', async () => {
    expect(parseDiscoverProjectDetail(detail).discoverGenerationId).toBe(board.generation);
    expect(() => parseDiscoverProjectDetail({
      ...detail,
      profile: { ...detail.profile, githubRepositoryId: 99 },
    })).toThrow('rardar_discover_project_invalid');
    const loaded = await loadDiscoverProjectDetail(42, board.generation!, async () => (
      new Response(JSON.stringify(detail), { status: 200 })
    ), 'http://backend.test');
    expect(loaded.kind).toBe('published');

    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={detail} />);
    expect(html).toContain('为什么现在出现在发现？');
    expect(html).toContain('实际窗口');
    expect(html).toContain('4 小时');
    expect(html).toContain('正增长区间');
    expect(html).toContain('最新区间增量');
    expect(html).toContain('下一次 Observation');
    expect(html).toContain('下一次 Today 结算');
    expect(html).toContain('为什么尚未进入 Today');
    expect(html).toContain('DiscoverFactContext');
    expect(html).toContain('生成 AI 深度解读');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture-lab%2Frealtime-project');
    expect(html).not.toContain('今日排名');
    expect(html).not.toContain('24 小时事实');
  });

  it('explains an outside-Today detail from deterministic audited facts', () => {
    const parsed = parseDiscoverProjectDetail(v3Detail);
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={parsed} />);

    expect(html).toContain('榜外异动');
    expect(html).toContain('完整 24h 事实 · Today Top 20 榜外');
    expect(html).toContain('Today 发布边界');
    expect(html).toContain('Top 20');
    expect(html).toContain('Today exact 排名');
    expect(html).toContain('#86');
    expect(html).toContain('最近 4 小时新增 12 Star');
    expect(html).toContain('最近实际 4 小时');
    expect(html).toContain('此前相同窗口的 3 Star');
    expect(html).toContain('短窗口加速');
    expect(html).toContain('+9 Star');
    expect(html).toContain('未进入 Top 20');
    expect(html).not.toContain('预测');
    expect(() => parseDiscoverProjectDetail({
      ...v3Detail,
      facts: { ...outsideCard, eligibilityClass: 'pre_exact' },
    })).toThrow('rardar_discover_project_invalid');
    expect(() => parseDiscoverProjectDetail({
      ...v3Detail,
      facts: { ...outsideCard, accelerationDelta: null },
    })).toThrow('rardar_discover_project_invalid');
  });
});
