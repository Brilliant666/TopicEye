import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RardarDiscoverPage from '@/components/RardarDiscoverPage';
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
  identitySummaryZh: '一个帮助开发者验证近实时项目变化的开源工具。',
  positioningZh: '通过连续观察与审计证据呈现项目的真实增长变化。',
  capabilities: [capability],
  sourceMode: 'rardar_derived',
  qualityState: 'partial',
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
  stageCounts: { justDiscovered: 1, rising: 0, nearValidation: 0 },
  stages: { justDiscovered: [card], rising: [], nearValidation: [] },
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
    officialZh: 0,
    officialTranslated: 0,
    rardarDerived: 1,
    githubRequests: 0,
    readmeCacheHits: 1,
    translationCalls: 0,
    translationCacheHits: 1,
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
  schemaVersion: 1,
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
} as unknown as DiscoverProjectDetail;

describe('Rardar near-real-time Discover', () => {
  it('renders three honest stages, actual windows, coverage, and internal detail navigation', () => {
    const html = renderToStaticMarkup(<RardarDiscoverPage result={{ kind: 'published', board }} />);

    expect(html).toContain('发现刚刚开始升温的项目');
    expect(html).toContain('每 2 小时');
    expect(html.indexOf('刚刚发现')).toBeLessThan(html.indexOf('持续升温'));
    expect(html.indexOf('持续升温')).toBeLessThan(html.indexOf('接近验证'));
    expect(html).toContain('+87');
    expect(html).toContain('/ 实际 4 小时');
    expect(html).toContain('本次已验证 Observation 中没有符合该阶段条件的项目');
    expect(html).toContain('/project/github/42?discoverGeneration=discover-generation-1');
    expect(html).toContain('Metadata failure 2');
    expect(html).toContain('不代表 GitHub 全站绝对完整扫描');
    expect(html).not.toContain('预计 24h');
    expect(html).not.toContain('全网排名');
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
      stages: { justDiscovered: [], rising: [], nearValidation: [] },
      code: 'rardar_discover_not_configured',
    }), { status: 503 }), 'http://backend.test');
    const invalid = await loadDiscover(async () => {
      throw new Error('offline');
    }, 'http://backend.test');
    expect(loaded.kind).toBe('published');
    expect(notConfigured).toEqual({ kind: 'not_configured', code: 'rardar_discover_not_configured' });
    expect(invalid).toEqual({ kind: 'invalid', code: 'rardar_discover_unavailable' });
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
    expect(html).toContain('近实时发现事实');
    expect(html).toContain('实际窗口');
    expect(html).toContain('4 小时');
    expect(html).toContain('生成 AI 深度解读');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture-lab%2Frealtime-project');
    expect(html).not.toContain('今日排名');
    expect(html).not.toContain('24 小时事实');
  });
});
