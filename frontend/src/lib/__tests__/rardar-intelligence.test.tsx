import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DiscoverFoundation, TodayFoundation } from '@/components/RardarFoundationPage';
import {
  loadExplosionBoard,
  loadTodaySnapshot,
  parseExplosionBoard,
  parseTodaySnapshot,
} from '@/lib/rardar-intelligence';

const readyPayload = {
  schemaVersion: 4,
  servingGenerationId: 'fixture-explosion-a--serving',
  profileSummary: {
    total: 2, complete: 2, partial: 0, sourceUnavailable: 0, chineseSummaries: 2,
    qualityReady: 2, qualityPartial: 0, qualityRejected: 0,
  },
  state: 'ready',
  reason: null,
  generationId: 'fixture-explosion-a',
  publishedAt: '2026-08-24T00:10:00Z',
  capturedAt: '2026-08-24T00:05:00Z',
  window: {
    state: 'exact',
    startedAt: '2026-08-23T00:00:00Z',
    endedAt: '2026-08-24T00:00:00Z',
    durationHours: 24,
    toleranceSeconds: 600,
  },
  coverage: {
    state: 'healthy',
    successfulQueryCount: 9,
    failedQueryCount: 0,
    metadataFailureCount: 0,
    exactCount: 2,
    pendingCount: 1,
    conflictCount: 0,
  },
  exactRanked: [
    {
      rank: 1,
      githubRepositoryId: 1,
      repository: 'fixture-lab/alpha',
      htmlUrl: 'https://github.com/fixture-lab/alpha',
      totalStars: 1200,
      baselineStars: 1000,
      observedStarDelta: 200,
      windowStartedAt: '2026-08-23T00:00:00Z',
      windowEndedAt: '2026-08-24T00:00:00Z',
      primaryLanguage: 'Python',
      topics: ['agents'],
      description: 'Alpha description',
      forks: 12,
      pushedAt: '2026-08-23T23:00:00Z',
      licenseSpdxId: 'MIT',
      archived: false,
      fork: false,
      mirrorUrl: null,
      state: 'exact_window',
      profileState: 'complete',
      officialSummaryZh: '一个经过官方资料约束的开源开发工具。',
      identitySummaryZh: '一个经过官方资料约束的开源开发工具。',
      coreValueZh: '把可组合开发能力与官方证据绑定，便于判断能否直接复用。',
      coreValueEvidenceRefs: ['readme:section:1'],
      keyDifferentiators: [{
        title: '证据约束',
        detail: '每项关键能力都保留官方资料引用。',
        shortDetail: '关键能力保留官方引用。',
        evidenceRefs: ['readme:section:1'],
      }],
      productFormsZh: ['开发组件'],
      qualityState: 'ready',
      qualityIssues: [],
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['提供可组合的开发能力'],
      capabilities: [{
        title: '可组合开发能力',
        detail: '提供可以嵌入既有工程流程的开发组件。',
        shortDetail: '可嵌入既有工程流程。',
        evidenceRefs: ['readme:section:1'],
      }],
      translationState: 'translated',
      officialTaglineZh: '一个经过官方资料约束的开源开发工具。',
      officialTaglineEvidenceRefs: ['readme:narrative:tagline'],
      officialPositioningZh: '该项目提供可组合的开发组件，可以嵌入既有工程流程。',
      officialPositioningEvidenceRefs: ['readme:narrative:positioning'],
      officialHighlights: [{
        sourceOrder: 1,
        sourceTitle: 'Composable building blocks',
        sourceDetail: 'Build workflows with components that fit existing projects.',
        titleZh: '可组合构件',
        detailZh: '用可以融入现有项目的组件构建工作流。',
        evidenceRefs: ['readme:narrative:highlight:1'],
      }],
      officialNarrativeMode: 'official_translated',
      officialNarrativeIssues: [],
      rardarAssessmentZh: '把可组合开发能力与官方证据绑定，便于判断能否直接复用。',
      rardarAssessmentEvidenceRefs: ['readme:section:1'],
      rardarDifferentiators: [{
        title: '证据约束',
        detail: '每项关键能力都保留官方资料引用。',
        shortDetail: '关键能力保留官方引用。',
        evidenceRefs: ['readme:section:1'],
      }],
    },
    {
      rank: 2,
      githubRepositoryId: 2,
      repository: 'fixture-lab/beta',
      htmlUrl: 'https://github.com/fixture-lab/beta',
      totalStars: 900,
      baselineStars: 800,
      observedStarDelta: 100,
      windowStartedAt: '2026-08-23T00:00:00Z',
      windowEndedAt: '2026-08-24T00:00:00Z',
      primaryLanguage: 'TypeScript',
      topics: ['developer-tools'],
      description: 'Beta description',
      forks: 8,
      pushedAt: '2026-08-23T22:00:00Z',
      licenseSpdxId: 'Apache-2.0',
      archived: false,
      fork: false,
      mirrorUrl: null,
      state: 'exact_window',
      profileState: 'complete',
      officialSummaryZh: '一个用于开发者工作流的开源项目。',
      identitySummaryZh: '一个用于开发者工作流的开源项目。',
      coreValueZh: '把重复任务组织成可复用的开发工作流。',
      coreValueEvidenceRefs: ['readme:section:2'],
      keyDifferentiators: [{
        title: '工作流自动化',
        detail: '把重复开发任务组织成可复用流程。',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      }],
      productFormsZh: ['工作流工具'],
      qualityState: 'ready',
      qualityIssues: [],
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['支持开发者自动化'],
      capabilities: [{
        title: '开发者自动化',
        detail: '支持把重复的开发者任务组织成自动化流程。',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      }],
      translationState: 'translated',
      officialTaglineZh: '一个用于开发者工作流的开源项目。',
      officialTaglineEvidenceRefs: ['readme:narrative:tagline'],
      officialPositioningZh: '该项目将重复的开发任务组织成可复用工作流。',
      officialPositioningEvidenceRefs: ['readme:narrative:positioning'],
      officialHighlights: [{
        sourceOrder: 1,
        sourceTitle: 'Workflow automation',
        sourceDetail: 'Turn repetitive developer tasks into reusable workflows.',
        titleZh: '工作流自动化',
        detailZh: '把重复的开发者任务组织成可复用工作流。',
        evidenceRefs: ['readme:narrative:highlight:1'],
      }],
      officialNarrativeMode: 'official_translated',
      officialNarrativeIssues: [],
      rardarAssessmentZh: '把重复任务组织成可复用的开发工作流。',
      rardarAssessmentEvidenceRefs: ['readme:section:2'],
      rardarDifferentiators: [{
        title: '工作流自动化',
        detail: '把重复开发任务组织成可复用流程。',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      }],
    },
  ],
  pendingRanked: [
    {
      pendingRank: 1,
      pendingReason: 'first_seen',
      githubRepositoryId: 3,
      repository: 'fixture-lab/newcomer',
      htmlUrl: 'https://github.com/fixture-lab/newcomer',
      totalStars: 300,
      firstSeenAt: '2026-08-23T12:05:00Z',
      observedWindowHours: 12,
      observedWindowStarDelta: 40,
      observedWindowStartedAt: '2026-08-23T12:05:00Z',
      observedWindowEndedAt: '2026-08-24T00:05:00Z',
      primaryLanguage: 'Go',
      topics: ['cli'],
      description: 'Newcomer description',
      forks: 2,
      pushedAt: '2026-08-23T22:30:00Z',
      licenseSpdxId: 'MIT',
    },
  ],
  conflictCount: 0,
  sourceStatus: {
    currentCaptureId: 'trending-v1-20260824T000000Z',
    baselineCaptureId: 'trending-v1-20260823T000000Z',
    partialCaptureCount: 1,
    coverageWitnessCaptureId: null,
  },
  dataMode: 'real',
  dataLabel: 'Rardar 生产快照',
  syncedAt: '2026-08-24T00:20:00Z',
  sourceHost: 'rardar-prod',
  manifestSha256: 'a'.repeat(64),
  artifactSha256: 'b'.repeat(64),
};

const v5ReadyPayload = {
  ...readyPayload,
  schemaVersion: 5,
  profileSummary: {
    ...readyPayload.profileSummary,
    officialZh: 0,
    officialTranslated: 2,
    rardarDerived: 0,
    insufficient: 0,
  },
};

const v6ReadyPayload = {
  ...v5ReadyPayload,
  schemaVersion: 6,
  exactRanked: v5ReadyPayload.exactRanked.map((project) => ({
    ...project,
    positioningZh: project.officialPositioningZh,
    positioningSourceMode: project.officialNarrativeMode,
    positioningEvidenceRefs: project.officialPositioningEvidenceRefs,
    positioningIncludedRoles: ['identity', 'core_mechanism', 'primary_outcome'],
    positioningExcludedClauses: [],
  })),
};

describe('Rardar intelligence client contract', () => {
  it('preserves the audited API order and rejects invented repository shapes', () => {
    const parsed = parseExplosionBoard(readyPayload);
    expect(parsed.exactRanked.map((item) => item.repository)).toEqual([
      'fixture-lab/alpha',
      'fixture-lab/beta',
    ]);
    expect(() =>
      parseExplosionBoard({
        ...readyPayload,
        exactRanked: [{ ...readyPayload.exactRanked[0], repository: 'invented' }],
      }),
    ).toThrow('rardar_response_invalid');
  });

  it('maps backend configuration and integrity failures to honest UI states', async () => {
    const notConfigured = await loadExplosionBoard(async () =>
      new Response(
        JSON.stringify({ detail: { code: 'rardar_intelligence_not_configured' } }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );
    const damaged = await loadExplosionBoard(async () =>
      new Response(
        JSON.stringify({ detail: { code: 'rardar_generation_invalid' } }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );

    expect(notConfigured).toEqual({ kind: 'not_configured' });
    expect(damaged).toEqual({ kind: 'error', code: 'rardar_generation_invalid' });
  });

  it('loads a Serving snapshot with bounded caching and maps its failure states', async () => {
    let requestedUrl = '';
    let requestedInit: RequestInit | undefined;
    const published = await loadTodaySnapshot(async (input, init) => {
      requestedUrl = input;
      requestedInit = init;
      return new Response(JSON.stringify(v5ReadyPayload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }, 'http://backend.test');
    const notConfigured = await loadTodaySnapshot(async () => new Response(
      JSON.stringify({ detail: { code: 'rardar_serving_unavailable' } }),
      { status: 503, headers: { 'content-type': 'application/json' } },
    ));
    const damaged = await loadTodaySnapshot(async () => new Response(
      JSON.stringify({ detail: { code: 'rardar_serving_hash_mismatch' } }),
      { status: 409, headers: { 'content-type': 'application/json' } },
    ));
    const unavailable = await loadTodaySnapshot(async () => {
      throw new Error('network unavailable');
    });

    expect(published.kind).toBe('published');
    expect(requestedUrl).toBe('http://backend.test/api/v1/rardar/today');
    expect(requestedInit).toMatchObject({
      cache: 'force-cache',
      next: { revalidate: 5 },
      headers: { Accept: 'application/json' },
    });
    expect(notConfigured).toEqual({ kind: 'not_configured' });
    expect(damaged).toEqual({ kind: 'error', code: 'rardar_serving_hash_mismatch' });
    expect(unavailable).toEqual({ kind: 'error', code: 'rardar_intelligence_unavailable' });
  });

  it('rejects malformed Serving profile metadata', () => {
    expect(parseTodaySnapshot({ ...readyPayload, schemaVersion: 4 }).schemaVersion).toBe(4);
    expect(parseTodaySnapshot(v5ReadyPayload).schemaVersion).toBe(5);
    expect(parseTodaySnapshot(v6ReadyPayload).schemaVersion).toBe(6);
    expect(() => parseTodaySnapshot({
      ...v6ReadyPayload,
      exactRanked: [{
        ...v6ReadyPayload.exactRanked[0],
        positioningSourceMode: 'invented',
      }],
      profileSummary: { ...v6ReadyPayload.profileSummary, total: 1, complete: 1, chineseSummaries: 1, qualityReady: 1, officialTranslated: 1 },
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...v6ReadyPayload,
      exactRanked: [{
        ...v6ReadyPayload.exactRanked[0],
        positioningIncludedRoles: ['identity', 'operation'],
      }],
      profileSummary: { ...v6ReadyPayload.profileSummary, total: 1, complete: 1, chineseSummaries: 1, qualityReady: 1, officialTranslated: 1 },
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...v5ReadyPayload,
      exactRanked: [{
        ...v5ReadyPayload.exactRanked[0],
        officialHighlights: [{
          ...v5ReadyPayload.exactRanked[0].officialHighlights[0],
          sourceOrder: 2,
        }],
      }],
      profileSummary: {
        ...v5ReadyPayload.profileSummary,
        total: 1,
        complete: 1,
        chineseSummaries: 1,
        qualityReady: 1,
        officialTranslated: 1,
      },
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...v5ReadyPayload,
      exactRanked: [{
        ...v5ReadyPayload.exactRanked[0],
        sourceLabel: 'Rardar 整理',
      }],
      profileSummary: {
        ...v5ReadyPayload.profileSummary,
        total: 1,
        complete: 1,
        chineseSummaries: 1,
        qualityReady: 1,
        officialTranslated: 1,
      },
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({ ...readyPayload, profileSummary: null })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], officialSummaryZh: '' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], capabilityBulletsZh: 'invented' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], keyDifferentiators: 'invented' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], coreValueEvidenceRefs: [7] }],
    })).toThrow('rardar_response_invalid');
  });

  it('renders the positioning without duplicating official highlights on Today cards', () => {
    const completeDetail = '将完整的官方能力说明连同证据保留下来，避免为了卡片高度截成无法理解的半句话。';
    const exactRanked = [{
      ...v5ReadyPayload.exactRanked[0],
      officialHighlights: [
        {
          sourceOrder: 1, sourceTitle: 'First', sourceDetail: completeDetail,
          titleZh: '作者第一项', detailZh: completeDetail, evidenceRefs: ['readme:narrative:highlight:1'],
        },
        {
          sourceOrder: 2, sourceTitle: 'Second', sourceDetail: 'Second detail',
          titleZh: '作者第二项', detailZh: '第二项完整能力提供可验证的工程交付。', evidenceRefs: ['readme:narrative:highlight:2'],
        },
        {
          sourceOrder: 3, sourceTitle: 'Third', sourceDetail: 'Third detail',
          titleZh: '作者第三项', detailZh: '第三项完整能力保留可追溯来源。', evidenceRefs: ['readme:narrative:highlight:3'],
        },
      ],
    }];
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...v5ReadyPayload,
          exactRanked,
          profileSummary: {
            ...v5ReadyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 1,
            officialTranslated: 1,
          },
        }),
      }} />,
    );

    expect(html).not.toContain(completeDetail);
    expect(html).not.toContain('作者第一项');
    expect(html).not.toContain('作者第二项');
    expect(html).not.toContain('第二项完整能力提供可验证的工程交付。');
    expect(html).not.toContain('作者第三项');
    expect(html).not.toContain('第三项完整能力保留可追溯来源。');
    expect(html).not.toContain('…');
    expect(html).toContain('核心定位 · 官方 README（译）');
    expect(html).not.toContain('把可组合开发能力与官方证据绑定');
    expect(html).toContain('/project/github/1?generation=fixture-explosion-a');
    expect(html).toContain('href="https://github.com/fixture-lab/alpha"');
    expect(html).not.toContain('用这个仓库评估我的需求');
  });

  it('uses the field-level positioning source without changing the overall narrative source', () => {
    const project = {
      ...v6ReadyPayload.exactRanked[0],
      sourceLabel: 'Rardar 整理',
      officialNarrativeMode: 'rardar_derived',
      officialNarrativeIssues: ['highlights_missing'],
      positioningSourceMode: 'official_zh',
      positioningZh: '一个采用官方中文定位、但其余画像由 Rardar 整理的项目。',
      officialPositioningZh: '一个采用官方中文定位、但其余画像由 Rardar 整理的项目。',
    };
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...v6ReadyPayload,
          exactRanked: [project],
          profileSummary: {
            ...v6ReadyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 1,
            officialTranslated: 0,
            rardarDerived: 1,
          },
        }),
      }} />,
    );

    expect(html).toContain('核心定位 · 官方中文 README');
    expect(html).toContain('一个采用官方中文定位、但其余画像由 Rardar 整理的项目。');
    expect(html).not.toContain('核心定位 · Rardar 整理');
  });

  it('renders audited DeepSeek and Ponytail positioning without operational or validation anecdotes', () => {
    const deepSeekPositioning = '以“一切皆插件”为架构，由 Cordis 驱动。';
    const ponytailPositioning = (
      '一套面向 AI 编程代理的技能、规则集与插件，指导代理先理解真实代码流程，'
      + '再选择尽可能精简且保留安全边界的实现。'
    );
    const deepSeek = {
      ...v6ReadyPayload.exactRanked[0],
      githubRepositoryId: 1333065091,
      repository: 'deepseek-ai/deepseek-harness',
      htmlUrl: 'https://github.com/deepseek-ai/deepseek-harness',
      sourceLabel: 'Rardar 整理',
      officialNarrativeMode: 'rardar_derived',
      officialNarrativeIssues: ['highlights_missing'],
      officialPositioningZh: deepSeekPositioning,
      officialPositioningEvidenceRefs: ['readme:narrative:positioning'],
      positioningZh: deepSeekPositioning,
      positioningSourceMode: 'official_zh',
      positioningEvidenceRefs: ['readme:narrative:positioning'],
      positioningIncludedRoles: ['core_mechanism'],
      positioningExcludedClauses: [],
      officialHighlights: [{
        sourceOrder: 1,
        sourceTitle: '运行',
        sourceDetail: '默认启动 Web UI，也可通过 SSH 仅启动服务器。',
        titleZh: '运行',
        detailZh: '默认启动 Web UI，也可通过 SSH 仅启动服务器。',
        evidenceRefs: ['readme:narrative:highlight:1'],
      }],
    };
    const ponytail = {
      ...v6ReadyPayload.exactRanked[1],
      githubRepositoryId: 1266797999,
      repository: 'DietrichGebert/ponytail',
      htmlUrl: 'https://github.com/DietrichGebert/ponytail',
      sourceLabel: 'Rardar 整理',
      officialNarrativeMode: 'rardar_derived',
      officialNarrativeIssues: ['source_structure_weak'],
      officialPositioningZh: ponytailPositioning,
      officialPositioningEvidenceRefs: ['readme:section:2'],
      positioningZh: ponytailPositioning,
      positioningSourceMode: 'rardar_derived',
      positioningEvidenceRefs: ['readme:section:2'],
      positioningIncludedRoles: ['identity', 'core_mechanism', 'primary_outcome'],
      positioningExcludedClauses: [{
        role: 'validation',
        text: '在真实 FastAPI 与 React 仓库的 Claude Code 会话中通过最终 Git diff 测量。',
        evidenceRefs: ['readme:section:3'],
      }],
      officialHighlights: [],
    };
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...v6ReadyPayload,
          exactRanked: [deepSeek, ponytail],
          profileSummary: {
            ...v6ReadyPayload.profileSummary,
            total: 2,
            complete: 2,
            chineseSummaries: 2,
            qualityReady: 2,
            officialTranslated: 0,
            rardarDerived: 2,
          },
        }),
      }} />,
    );

    expect(html).toContain(deepSeekPositioning);
    expect(html).toContain('核心定位 · 官方中文 README');
    expect(html).toContain(ponytailPositioning);
    expect(html).toContain('核心定位 · Rardar 整理');
    expect(ponytailPositioning.startsWith('Ponytail 是')).toBe(false);
    for (const leakage of ['Web UI', 'SSH', '仅启动服务器', 'FastAPI', 'React', 'Claude Code', 'Git diff']) {
      expect(html).not.toContain(leakage);
    }
  });

  it('labels a derived narrative as Rardar 整理 instead of official content', () => {
    const project = {
      ...v5ReadyPayload.exactRanked[0],
      sourceLabel: 'Rardar 整理',
      officialNarrativeMode: 'rardar_derived',
      officialNarrativeIssues: ['source_structure_weak'],
    };
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...v5ReadyPayload,
          exactRanked: [project],
          profileSummary: {
            ...v5ReadyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 1,
            officialTranslated: 0,
            rardarDerived: 1,
          },
        }),
      }} />,
    );

    expect(html).toContain('核心定位 · Rardar 整理');
    expect(html).not.toContain('核心定位 · 官方 README（译）');
  });

  it('keeps Serving v1, v2, and v3 snapshots readable without inventing v4 semantic fields', () => {
    const v4Fields = new Set([
      'identitySummaryZh', 'coreValueZh', 'coreValueEvidenceRefs', 'keyDifferentiators',
      'productFormsZh', 'qualityState', 'qualityIssues',
    ]);
    for (const schemaVersion of [1, 2, 3]) {
      const legacy = {
        ...readyPayload,
        schemaVersion,
        exactRanked: readyPayload.exactRanked.map((project) => Object.fromEntries(
          Object.entries(project).filter(([key]) => !v4Fields.has(key) && (schemaVersion >= 3 || key !== 'capabilities')),
        )),
      };
      const parsed = parseTodaySnapshot(legacy);
      expect(parsed.schemaVersion).toBe(schemaVersion);
      expect(parsed.exactRanked.every((project) => project.coreValueZh === null)).toBe(true);
      expect(parsed.exactRanked.every((project) => project.qualityState === 'partial')).toBe(true);
      if (schemaVersion < 3) {
        expect(parsed.exactRanked.every((project) => project.capabilities.length === 0)).toBe(true);
      }
    }
  });

  it('renders server HTML from facts without inventing AI explanations', () => {
    const html = renderToStaticMarkup(
      <TodayFoundation result={{ kind: 'published', board: parseTodaySnapshot(readyPayload) }} />,
    );

    expect(html).toContain('fixture-lab/alpha');
    expect(html).toContain('+200');
    expect(html).not.toContain('fixture-lab/newcomer');
    expect(html).toContain('发现 1 个正在积累观察的项目');
    expect(html).toContain('精确 24h');
    expect(html).toContain('查看项目详情');
    expect(html).not.toContain('生成 AI 深度解读');
    expect(html).not.toContain('爆发原因：');
  });

  it('isolates a rejected profile and preserves only verified repository and Star facts', () => {
    const unsafe = 'https://github.com/user-attachments/assets/deadbeef';
    const rejected = {
      ...v5ReadyPayload.exactRanked[0],
      officialSummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
      identitySummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
      coreValueZh: null,
      coreValueEvidenceRefs: [],
      keyDifferentiators: [],
      capabilities: [],
      capabilityBulletsZh: [],
      productFormsZh: [],
      qualityState: 'rejected',
      qualityIssues: ['identity_source_rejected'],
      description: unsafe,
      sourceLabel: '受限概括',
      officialTaglineZh: null,
      officialTaglineEvidenceRefs: [],
      officialPositioningZh: null,
      officialPositioningEvidenceRefs: [],
      officialHighlights: [],
      officialNarrativeMode: 'insufficient',
      officialNarrativeIssues: ['official_narrative_insufficient'],
      rardarAssessmentZh: null,
      rardarAssessmentEvidenceRefs: [],
      rardarDifferentiators: [],
    };
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...v5ReadyPayload,
          exactRanked: [rejected],
          profileSummary: {
            ...v5ReadyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 0,
            qualityRejected: 1,
            officialTranslated: 0,
            insufficient: 1,
          },
        }),
      }} />,
    );

    expect(html).toContain('官方资料不足');
    expect(html).toContain('+200');
    expect(html).not.toContain(unsafe);
    expect(html).not.toContain('核心定位 · 官方');
  });

  it('renders Discover from pending only without 24h extrapolation', () => {
    const html = renderToStaticMarkup(
      <DiscoverFoundation result={{ kind: 'published', board: parseExplosionBoard(readyPayload) }} />,
    );
    expect(html).toContain('fixture-lab/newcomer');
    expect(html).not.toContain('fixture-lab/alpha');
    expect(html).toContain('观察中');
    expect(html).toContain('12.0h');
    expect(html).toContain('AI 解读');
    expect(html).not.toContain('生成 AI 深度解读');
    expect(html).not.toContain('预计 24');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture-lab%2Fnewcomer');
  });

  it('keeps the first ten visible and places ranks 11-20 behind an explicit expansion', () => {
    const exactRanked = Array.from({ length: 20 }, (_, index) => ({
      ...readyPayload.exactRanked[0],
      rank: index + 1,
      githubRepositoryId: index + 100,
      repository: `fixture-lab/project-${index + 1}`,
      htmlUrl: `https://github.com/fixture-lab/project-${index + 1}`,
      observedStarDelta: 1000 - index,
    }));
    const html = renderToStaticMarkup(
      <TodayFoundation result={{ kind: 'published', board: parseTodaySnapshot({ ...readyPayload, exactRanked, profileSummary: { ...readyPayload.profileSummary, total: 20, chineseSummaries: 20, complete: 20, qualityReady: 20 } }) }} />,
    );
    expect(html).toContain('GitHub 精确 24 小时爆发榜 Top 10');
    expect(html).toContain('查看 Top 20');
    expect(html).toContain('<details');
    expect(html).toContain('第 11 至 20 名');
  });

  it.each([
    [{ kind: 'not_configured' } as const, '真实数据尚未同步'],
    [{ kind: 'error', code: 'rardar_generation_invalid' } as const, '真实情报数据暂时不可用'],
    [
      {
        kind: 'published',
        board: parseTodaySnapshot({
          ...readyPayload,
          profileSummary: {
            total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0,
            qualityReady: 0, qualityPartial: 0, qualityRejected: 0,
          },
          state: 'warming_up',
          window: { ...readyPayload.window, state: 'warming_up' },
          exactRanked: [],
        }),
      } as const,
      '尚未形成完整 24 小时精确榜',
    ],
    [
      {
        kind: 'published',
        board: parseTodaySnapshot({
          ...readyPayload,
          profileSummary: {
            total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0,
            qualityReady: 0, qualityPartial: 0, qualityRejected: 0,
          },
          state: 'baseline_missing',
          window: { ...readyPayload.window, state: 'baseline_missing' },
          exactRanked: [],
        }),
      } as const,
      '尚未形成完整 24 小时精确榜',
    ],
  ])('renders a truthful non-ready state', (result, expected) => {
    const html = renderToStaticMarkup(<TodayFoundation result={result} />);
    expect(html).toContain(expected);
    if (result.kind === 'published') expect(html).not.toContain('fixture-lab/newcomer');
  });

  it('accepts an explicit not-synced real state without fabricated generation metadata', () => {
    const html = renderToStaticMarkup(<TodayFoundation result={{ kind: 'not_configured' }} />);
    expect(html).toContain('真实数据尚未同步');
    expect(html).toContain('sync-data');
    expect(html).not.toContain('本地演示数据');
  });
});
