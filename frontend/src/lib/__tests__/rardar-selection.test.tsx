import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RardarSelectionDetailPage from '@/components/RardarSelectionDetailPage';
import RardarSelectionPage, { filterSelection } from '@/components/RardarSelectionPage';
import {
  loadSelection,
  loadSelectionProjectDetail,
  parseSelectionProjectDetail,
  parseSelectionResponse,
  type SelectionCard,
  type SelectionProjectDetail,
  type SelectionResponse,
} from '@/lib/rardar-selection';

const card: SelectionCard = {
  githubRepositoryId: 42,
  repository: 'fixture-lab/reusable-toolkit',
  htmlUrl: 'https://github.com/fixture-lab/reusable-toolkit',
  identitySummaryZh: '一个提供可组合 SDK 与命令行工作流的开发工具。',
  corePositioningZh: '将可组合 SDK、适配器和命令行入口组织为可验证的自动化工具链。',
  whyWorthSeeingZh: '它提供可以直接检查和接入的 SDK、示例与模块边界。',
  whyNowZh: '近期发布包含有证据支持的实质能力变化。',
  primaryReason: 'directly_reusable',
  supportingReasons: ['distinctive_implementation'],
  category: 'dev-tools',
  categorySource: 'research_derived',
  productFormsZh: ['开发工具', 'SDK'],
  primaryLanguage: 'Python',
  topics: ['sdk', 'automation'],
  licenseSpdxId: 'MIT',
  totalStars: 1287,
  momentumLabel: '已观察 26h +87 Star',
  reusableAssets: ['SDK', '命令行工作流'],
  bestFit: ['需要组合自动化能力的开发者'],
};

const selection: SelectionResponse = {
  mode: 'shadow',
  status: 'ready',
  state: 'ready',
  generation: 'selection-generation-1',
  sourceObservation: 'observation-v1-source-1',
  sourceTodayGeneration: 'today-generation-1',
  generatedAt: '2026-09-03T02:00:00Z',
  latestCaptureAt: '2026-09-03T00:00:00Z',
  items: [card],
  categoryCounts: { 'dev-tools': 1 },
  primaryReasonCounts: { directly_reusable: 1 },
  coverageLabelZh: '基于已验证 Observation 历史形成的本地精选，不代表全部 GitHub。',
  candidateCount: 475,
  selectedCount: 1,
  publishedCount: 1,
  suppressedCount: 0,
  provenance: { mode: 'shadow', sourceTodayGeneration: 'today-generation-1' },
  code: null,
  currentGeneration: 'selection-generation-1',
  latestAttemptGeneration: 'selection-generation-1',
  recallCount: 1,
  profileReadyCount: 1,
  profileReboundCount: 0,
  profileRebuiltCount: 1,
  retryableFailureCount: 0,
  permanentFailureCount: 0,
  profileCoverage: 1,
  assessmentCoverage: 1,
  systemicFailure: false,
  safeFailureCodes: [],
  nextRetryAt: null,
};

const detail: SelectionProjectDetail = {
  selectionGenerationId: selection.generation!,
  sourceObservationSetId: selection.sourceObservation!,
  context: {
    schemaVersion: 1,
    selectionGenerationId: selection.generation!,
    sourceObservationSetId: selection.sourceObservation!,
    generatedAt: '2026-09-03T02:00:00Z',
    card,
    selectionEvidenceDigest: 'a'.repeat(64),
    timelinessReasonCodes: ['meaningful_release'],
    evidence: [{
      evidenceId: 'E01',
      sourceType: 'description',
      sourcePath: 'repository.description',
      sourceRevision: 'source-revision-1',
      excerpt: 'A reusable SDK and CLI toolkit.',
      githubRepositoryId: 42,
    }],
    canonicalProfile: {
      githubRepositoryId: 42,
      repository: card.repository,
      capabilities: [{ title: '可组合 SDK', detail: '提供可验证的模块化接口。' }],
      startHere: [{
        label: 'README',
        path: 'README.md',
        htmlUrl: `${card.htmlUrl}/blob/main/README.md`,
      }],
    },
    canonicalEvidence: {
      githubRepositoryId: 42,
      repository: card.repository,
    },
  },
};

describe('Rardar worth-seeing Selection', () => {
  it('strictly parses one unranked Selection and rejects mixed identities', () => {
    expect(parseSelectionResponse(selection).items).toHaveLength(1);
    expect(() => parseSelectionResponse({ ...selection, items: [card, card] })).toThrow(
      'rardar_selection_response_invalid',
    );
    expect(() => parseSelectionProjectDetail({
      ...detail,
      context: { ...detail.context, selectionGenerationId: 'other-generation' },
    })).toThrow('rardar_selection_detail_invalid');
  });

  it('keeps an empty immutable generation readable after it becomes stale', () => {
    const staleEmpty = {
      ...selection,
      status: 'stale' as const,
      state: 'stale' as const,
      items: [],
      categoryCounts: {},
      primaryReasonCounts: {},
      selectedCount: 0,
      publishedCount: 0,
    };
    expect(parseSelectionResponse(staleEmpty).items).toEqual([]);
  });

  it('renders a legitimate empty result only after complete assessment', () => {
    const empty = {
      ...selection,
      status: 'empty' as const,
      state: 'empty' as const,
      items: [],
      categoryCounts: {},
      primaryReasonCounts: {},
      selectedCount: 0,
      publishedCount: 0,
    };
    const html = renderToStaticMarkup(
      <RardarSelectionPage result={{ kind: 'published', selection: empty }} />,
    );
    expect(html).toContain('这是有效的空结果');
    expect(html).not.toContain('项目画像覆盖不足');
  });

  it('labels a degraded rebuild while retaining the last healthy items', () => {
    const degraded = {
      ...selection,
      status: 'degraded' as const,
      state: 'degraded' as const,
      latestAttemptGeneration: 'selection-generation-degraded',
      recallCount: 48,
      profileReadyCount: 2,
      retryableFailureCount: 46,
      profileCoverage: 2 / 48,
      assessmentCoverage: 1,
      systemicFailure: true,
      safeFailureCodes: ['profile_source_http_5xx'],
      code: 'rardar_selection_degraded',
    };
    const parsed = parseSelectionResponse(degraded);
    const html = renderToStaticMarkup(
      <RardarSelectionPage result={{ kind: 'published', selection: parsed }} />,
    );
    expect(html).toContain('正在恢复最新画像');
    expect(html).toContain('暂时展示上一份健康精选');
    expect(html).toContain(card.repository);
    expect(html).not.toContain('当前没有值得看的项目');
  });

  it('does not mislabel degraded-without-current as an empty selection', () => {
    const degraded = {
      ...selection,
      status: 'degraded' as const,
      state: 'degraded' as const,
      generation: null,
      currentGeneration: null,
      latestAttemptGeneration: 'selection-generation-degraded',
      items: [],
      categoryCounts: {},
      primaryReasonCounts: {},
      selectedCount: 0,
      publishedCount: 0,
      recallCount: 48,
      profileReadyCount: 2,
      retryableFailureCount: 46,
      profileCoverage: 2 / 48,
      assessmentCoverage: 1,
      systemicFailure: true,
      safeFailureCodes: ['profile_source_http_5xx'],
      code: 'rardar_selection_degraded',
    };
    const parsed = parseSelectionResponse(degraded);
    const html = renderToStaticMarkup(
      <RardarSelectionPage result={{ kind: 'published', selection: parsed }} />,
    );
    expect(html).toContain('本轮精选结果尚未发布');
    expect(html).toContain('最新精选尚未发布');
    expect(html).not.toContain('这是有效的空结果');
  });

  it('renders an integrity-safe invalid state without internal details', () => {
    const html = renderToStaticMarkup(
      <RardarSelectionPage result={{ kind: 'invalid', code: 'rardar_selection_invalid' }} />,
    );
    expect(html).toContain('精选数据未通过完整性验证');
    expect(html).toContain('rardar_selection_invalid');
    expect(html).not.toContain('Traceback');
  });

  it('renders a single stream with no public rank or confidence', () => {
    const html = renderToStaticMarkup(
      <RardarSelectionPage result={{ kind: 'published', selection }} />,
    );
    expect(html).toContain('本轮值得看的项目');
    expect(html).toContain(card.repository);
    expect(html).toContain('为什么值得看');
    expect(html).toContain('不公开排名');
    expect(html).not.toContain('confidence');
    expect(html).not.toContain('综合分');
    expect(html).toContain(
      `/project/github/42?selectionGeneration=${selection.generation}`,
    );
  });

  it('filters only by explicit category and primary reason', () => {
    expect(filterSelection([card], 'dev-tools', 'directly_reusable')).toEqual([card]);
    expect(filterSelection([card], 'ai-agent', 'all')).toEqual([]);
    expect(filterSelection([card], 'all', 'reference_or_learning_value')).toEqual([]);
  });

  it('renders static detail from canonical profile and selection evidence', () => {
    const parsed = parseSelectionProjectDetail(detail);
    const html = renderToStaticMarkup(<RardarSelectionDetailPage detail={parsed} />);
    expect(html).toContain(card.repository);
    expect(html).toContain('Canonical Project Profile');
    expect(html).toContain('可组合 SDK');
    expect(html).toContain('E01 · description');
    expect(html).toContain('/find?repositoryUrl=');
  });

  it('fails closed for unavailable list and detail responses', async () => {
    const unavailable = await loadSelection(async () => {
      throw new Error('offline');
    });
    expect(unavailable).toEqual({ kind: 'invalid', code: 'rardar_selection_unavailable' });

    const missing = await loadSelectionProjectDetail(
      42,
      selection.generation!,
      async () => new Response(JSON.stringify({ detail: { code: 'missing' } }), { status: 404 }),
    );
    expect(missing).toEqual({ kind: 'not_found' });
  });
});
