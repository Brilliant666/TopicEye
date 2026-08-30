import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { loadProjectDetail, parseProjectDetail, type ProjectDetail } from '@/lib/rardar-intelligence';

const officialTaglineZh = '在对话里，把代码仓库或系统描述变成漂亮、可靠、可交互的系统地图。';
const officialPositioningZh = 'Archify 是一套基于 Node.js 的渲染与校验系统，并以 Agent Skill 的形式支持 Raven、Cursor、Claude Code、Codex CLI 和 OpenCode。Agent 负责生成 Typed JSON IR，Archify 再校验并确定性编译为便携、独立的 HTML/SVG 成品。';
const officialHighlights = [
  {
    sourceOrder: 1,
    sourceTitle: '打开就是成品',
    sourceDetail: '五种技术图、四套视觉预设、深浅主题、内置品牌徽标，以及显式启用的有限动态。',
    titleZh: '打开就是成品',
    detailZh: '五种技术图、四套视觉预设、深浅主题、内置品牌徽标，以及显式启用的有限动态。',
    evidenceRefs: ['readme:narrative:highlight:1'],
  },
  {
    sourceOrder: 2,
    sourceTitle: '合并前先看清架构变化',
    sourceDetail: '把两份已校验快照对比为 Before / Delta / After，准确区分新增、删除、语义变化、移动和重路由。',
    titleZh: '合并前先看清架构变化',
    detailZh: '把两份已校验快照对比为 Before / Delta / After，准确区分新增、删除、语义变化、移动和重路由。',
    evidenceRefs: ['readme:narrative:highlight:2'],
  },
  {
    sourceOrder: 3,
    sourceTitle: '每次探索都有依据',
    sourceDetail: '搜索节点、按需打开版本校验过的源码、追踪作者定义的上下游可达范围与精确路径、对比角色、播放故事，但不编造拓扑。',
    titleZh: '每次探索都有依据',
    detailZh: '搜索节点、按需打开版本校验过的源码、追踪作者定义的上下游可达范围与精确路径、对比角色、播放故事，但不编造拓扑。',
    evidenceRefs: ['readme:narrative:highlight:3'],
  },
  {
    sourceOrder: 4,
    sourceTitle: '一个文件即可放心交付',
    sourceDetail: 'Typed JSON IR 和确定性校验生成独立 HTML，并支持 PNG、SVG、WebM 与 1200×630 分享卡片。',
    titleZh: '一个文件即可放心交付',
    detailZh: 'Typed JSON IR 和确定性校验生成独立 HTML，并支持 PNG、SVG、WebM 与 1200×630 分享卡片。',
    evidenceRefs: ['readme:narrative:highlight:4'],
  },
];
const rardarAssessmentZh = '通过 Typed JSON IR、Schema 和确定性校验，将生成结果约束为可追溯、可复现的工程交付物，而不只是生成一张外观合理的图。';
const rardarDifferentiators = [
  {
    title: '确定性中间表示',
    detail: '使用类型化 JSON 中间表示和校验机制组织架构事实。',
    shortDetail: '用类型化 JSON 与校验组织架构事实。',
    evidenceRefs: ['readme:section:1'],
  },
  {
    title: '路径级证据',
    detail: '把图中节点回指到对应的仓库路径和官方证据。',
    shortDetail: '把节点回指到仓库路径。',
    evidenceRefs: ['readme:section:2'],
  },
];

const detail: ProjectDetail = {
  schemaVersion: 5,
  generationId: 'generation-v1',
  servingGenerationId: 'generation-v1--serving',
  project: {
    rank: 1,
    githubRepositoryId: 1211139949,
    repository: 'tt-a1i/archify',
    htmlUrl: 'https://github.com/tt-a1i/archify',
    totalStars: 23114,
    baselineStars: 17868,
    observedStarDelta: 5246,
    windowStartedAt: '2026-08-27T00:00:00Z',
    windowEndedAt: '2026-08-28T00:00:00Z',
    primaryLanguage: 'JavaScript',
    topics: ['architecture-as-code', 'code-visualization'],
    description: 'Generate architecture diagrams from code.',
    forks: 1000,
    pushedAt: '2026-08-27T06:49:25Z',
    defaultBranch: 'main',
    licenseSpdxId: 'MIT',
    archived: false,
    fork: false,
    mirrorUrl: null,
    state: 'exact_window',
    profileState: 'complete',
    officialSummaryZh: officialTaglineZh,
    identitySummaryZh: officialTaglineZh,
    coreValueZh: rardarAssessmentZh,
    coreValueEvidenceRefs: ['readme:section:1', 'readme:section:2'],
    keyDifferentiators: rardarDifferentiators,
    productFormsZh: ['Agent Skill', 'Node.js 渲染/校验工具'],
    qualityState: 'ready',
    qualityIssues: [],
    sourceLabel: '官方中文 README',
    sourceLanguage: 'zh',
    capabilityBulletsZh: ['生成独立 HTML / SVG 架构图', '对比架构快照变化', '追踪节点对应的代码路径'],
    capabilities: [
      {
        title: '技术图与交互展示',
        detail: '生成独立 HTML / SVG 架构图',
        shortDetail: '生成可独立打开的架构交付。',
        evidenceRefs: ['readme:section:1', 'readme:section:2'],
      },
      {
        title: '架构变化对比',
        detail: '对比架构快照变化',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      },
      {
        title: '可追溯架构探索',
        detail: '追踪节点对应的代码路径',
        shortDetail: null,
        evidenceRefs: ['readme:section:3'],
      },
    ],
    translationState: 'not_needed',
    officialTaglineZh,
    officialTaglineEvidenceRefs: ['readme:narrative:tagline'],
    officialPositioningZh,
    officialPositioningEvidenceRefs: ['readme:narrative:positioning'],
    positioningZh: officialPositioningZh,
    positioningSourceMode: 'official_zh',
    positioningEvidenceRefs: ['readme:narrative:positioning'],
    positioningIncludedRoles: ['identity', 'core_mechanism', 'primary_outcome'],
    positioningExcludedClauses: [],
    officialHighlights,
    officialNarrativeMode: 'official_zh',
    officialNarrativeIssues: [],
    rardarAssessmentZh,
    rardarAssessmentEvidenceRefs: ['readme:section:1', 'readme:section:2'],
    rardarDifferentiators,
  },
  profile: {
    profileSchemaVersion: 'rardar-project-profile-v5',
    promptVersion: 'rardar-project-profile-zh-v7',
    githubRepositoryId: 1211139949,
    repository: 'tt-a1i/archify',
    htmlUrl: 'https://github.com/tt-a1i/archify',
    generationId: 'generation-v1',
    profileState: 'complete',
    officialSummaryZh: officialTaglineZh,
    identitySummaryZh: officialTaglineZh,
    coreValueZh: rardarAssessmentZh,
    coreValueEvidenceRefs: ['readme:section:1', 'readme:section:2'],
    keyDifferentiators: rardarDifferentiators,
    qualityState: 'ready',
    qualityIssues: [],
    sourceLabel: '官方中文 README',
    sourceLanguage: 'zh',
    capabilityBulletsZh: ['生成独立 HTML / SVG 架构图', '对比架构快照变化', '追踪节点对应的代码路径'],
    capabilities: [
      {
        title: '技术图与交互展示',
        detail: '生成独立 HTML / SVG 架构图',
        shortDetail: '生成可独立打开的架构交付。',
        evidenceRefs: ['readme:section:1', 'readme:section:2'],
      },
      {
        title: '架构变化对比',
        detail: '对比架构快照变化',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      },
      {
        title: '可追溯架构探索',
        detail: '追踪节点对应的代码路径',
        shortDetail: null,
        evidenceRefs: ['readme:section:3'],
      },
    ],
    productFormsZh: ['Agent Skill', 'Node.js 渲染/校验工具'],
    supportedEnvironmentsZh: ['Raven', 'Cursor', 'Claude Code', 'Codex CLI'],
    primaryUseCasesZh: ['理解陌生代码库的系统结构'],
    deliveryFormsZh: ['独立 HTML', 'SVG'],
    claimEvidenceRefs: {
      '根据代码仓库生成可交互架构图，并保留路径证据。': ['readme:section:1'],
      '通过类型化 JSON 中间表示与确定性校验，把架构图绑定到可追溯的仓库证据。': ['readme:section:1', 'readme:section:2'],
    },
    readmePath: 'README.md',
    readmeBlobSha: 'a'.repeat(40),
    selectedSections: [{
      heading: 'Overview', path: 'README.md#overview', purpose: 'overview',
      excerpts: ['Generate interactive architecture diagrams.'], listItems: [], evidenceRefs: ['readme:section:1'],
    }],
    originalExcerpts: ['Generate interactive architecture diagrams.'],
    startHere: [
      {
        label: 'README · Overview', path: 'README.md#overview',
        htmlUrl: 'https://github.com/tt-a1i/archify/blob/main/README.md#overview', evidenceRefs: ['readme:section:1'],
      },
      {
        label: 'README · Features', path: 'README.md#features',
        htmlUrl: 'https://github.com/tt-a1i/archify/blob/main/README.md#features', evidenceRefs: ['readme:section:2'],
      },
      {
        label: '快速开始', path: 'README.md#quick-start',
        htmlUrl: 'https://github.com/tt-a1i/archify/blob/main/README.md#quick-start', evidenceRefs: ['readme:section:3'],
      },
      {
        label: '实现与架构', path: 'docs/architecture.md',
        htmlUrl: 'https://github.com/tt-a1i/archify/blob/main/docs/architecture.md', evidenceRefs: ['readme:section:4'],
      },
      {
        label: '更多示例', path: 'examples',
        htmlUrl: 'https://github.com/tt-a1i/archify/tree/main/examples', evidenceRefs: ['path:examples'],
      },
    ],
    evidenceDigest: 'b'.repeat(64),
    generatedAt: '2026-08-28T01:00:00Z',
    translationState: 'not_needed',
    officialTaglineZh,
    officialTaglineEvidenceRefs: ['readme:narrative:tagline'],
    officialPositioningZh,
    officialPositioningEvidenceRefs: ['readme:narrative:positioning'],
    positioningZh: officialPositioningZh,
    positioningSourceMode: 'official_zh',
    positioningEvidenceRefs: ['readme:narrative:positioning'],
    positioningIncludedRoles: ['identity', 'core_mechanism', 'primary_outcome'],
    positioningExcludedClauses: [],
    officialHighlights,
    officialNarrativeMode: 'official_zh',
    officialNarrativeIssues: [],
    officialNarrativePromptVersion: 'rardar-official-narrative-zh-v1',
    rardarAssessmentZh,
    rardarAssessmentEvidenceRefs: ['readme:section:1', 'readme:section:2'],
    rardarDifferentiators,
    rardarAssessmentPromptVersion: 'rardar-project-assessment-zh-v1',
  },
  coverage: {
    state: 'degraded', successfulQueryCount: 8, failedQueryCount: 1, metadataFailureCount: 1,
    exactCount: 20, pendingCount: 12, conflictCount: 14,
  },
  conflictCount: 14,
  evidence: {
    schemaVersion: 1,
    githubRepositoryId: 1211139949,
    repository: 'tt-a1i/archify',
    generationId: 'generation-v1',
    readmePath: 'README.md',
    readmeBlobSha: 'a'.repeat(40),
    sourceLanguage: 'en',
    selectedSections: [],
    originalExcerpts: [],
    topLevelTree: [{ path: 'README.md', type: 'file' }],
    evidenceIndex: { 'readme:section:1': 'README.md: Overview' },
    pathRefs: { 'readme:section:1': 'README.md#overview' },
    digest: 'b'.repeat(64),
  },
};

describe('Rardar project detail', () => {
  it('renders identity, value, adoption, onboarding, facts, and folded provenance in order', () => {
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={detail} />);

    expect(html).toContain('tt-a1i/archify');
    expect(html).toContain(officialTaglineZh);
    expect(html).toContain(officialPositioningZh);
    expect(html).toContain('打开就是成品');
    expect(html).toContain('合并前先看清架构变化');
    expect(html).toContain('每次探索都有依据');
    expect(html).toContain('一个文件即可放心交付');
    expect(html.indexOf('打开就是成品')).toBeLessThan(html.indexOf('合并前先看清架构变化'));
    expect(html.indexOf('合并前先看清架构变化')).toBeLessThan(html.indexOf('每次探索都有依据'));
    expect(html.indexOf('每次探索都有依据')).toBeLessThan(html.indexOf('一个文件即可放心交付'));
    expect(html).toContain('Agent Skill');
    expect(html).toContain('Claude Code');
    expect(html).toContain('独立 HTML');
    expect(html).toContain('核心定位 · 官方中文 README');
    expect(html).toContain('它能做什么');
    expect(html).toContain('Rardar 决策与采用');
    expect(html).toContain('Rardar 判断');
    expect(html).toContain(rardarAssessmentZh);
    expect(html).toContain('如何开始');
    expect(html).toContain('24 小时事实');
    expect(html).toContain('+5,246');
    expect(html).toContain('README.md#overview');
    expect(html).toContain('来源、官方原文与审计');
    expect(html).toContain('1 个 metadata failure');
    expect(html).toContain('14 个负增长冲突');
    expect(html).toContain('生成 AI 深度解读');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ftt-a1i%2Farchify');
    expect(html).not.toContain('稳定性仍需验证');
    expect(html).toContain('官方 README');
    expect(html.indexOf(officialPositioningZh)).toBeLessThan(html.indexOf(rardarAssessmentZh));
    const officialBlock = html.slice(
      html.indexOf('data-testid="project-official-positioning"'),
      html.indexOf('它能做什么'),
    );
    const adoptionBlock = html.slice(
      html.indexOf('data-testid="rardar-adoption-layer"'),
      html.indexOf('如何开始'),
    );
    expect(officialBlock).not.toContain(rardarAssessmentZh);
    expect(adoptionBlock).toContain(rardarAssessmentZh);
    expect(html.indexOf('生成 AI 深度解读')).toBeLessThan(html.indexOf('如何开始'));
    expect((html.match(/用这个仓库评估我的需求/g) || [])).toHaveLength(1);
    expect((html.match(/#1/g) || [])).toHaveLength(1);
    expect((html.match(/\+5,246/g) || [])).toHaveLength(1);
    expect(html).toContain('更多官方资料（1）');
    expect(html).toContain('<details class="');
    expect(html).not.toContain('<details open');
  });

  it('rejects a generation or identity mismatch at the client boundary', () => {
    expect(() => parseProjectDetail({ ...detail, generationId: 'other-generation' })).toThrow(
      'rardar_project_response_invalid',
    );
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, githubRepositoryId: 7 },
    })).toThrow('rardar_project_response_invalid');
  });

  it('keeps a v1 Serving detail readable while defaulting new evidence-backed fields to hidden', () => {
    const legacy = {
      ...detail,
      schemaVersion: 1,
      profile: {
        ...detail.profile,
        profileSchemaVersion: 'rardar-project-profile-v1',
        promptVersion: 'rardar-project-profile-zh-v2',
        capabilities: undefined,
        identitySummaryZh: undefined,
        coreValueZh: undefined,
        coreValueEvidenceRefs: undefined,
        keyDifferentiators: undefined,
        qualityState: undefined,
        qualityIssues: undefined,
        productFormsZh: undefined,
        supportedEnvironmentsZh: undefined,
      },
      coverage: undefined,
      conflictCount: undefined,
    };

    const parsed = parseProjectDetail(legacy);
    expect(parsed.profile.productFormsZh).toEqual([]);
    expect(parsed.profile.supportedEnvironmentsZh).toEqual([]);
    expect(parsed.profile.capabilities).toEqual([]);
    expect(parsed.coverage).toBeNull();
    expect(parsed.conflictCount).toBe(0);
  });

  it('keeps a v2 Serving detail readable without structured capability duplication', () => {
    const legacy = {
      ...detail,
      schemaVersion: 2,
      project: { ...detail.project, capabilities: undefined },
      profile: {
        ...detail.profile,
        profileSchemaVersion: 'rardar-project-profile-v2',
        promptVersion: 'rardar-project-profile-zh-v3',
        capabilities: undefined,
        identitySummaryZh: undefined,
        coreValueZh: undefined,
        coreValueEvidenceRefs: undefined,
        keyDifferentiators: undefined,
        qualityState: undefined,
        qualityIssues: undefined,
      },
    };
    const parsed = parseProjectDetail(legacy);
    expect(parsed.profile.capabilities).toEqual([]);
  });

  it('loads an immutable detail by numeric identity and encoded generation', async () => {
    let requestedUrl = '';
    let requestedInit: RequestInit | undefined;
    const result = await loadProjectDetail(1211139949, 'generation/v1', async (input, init) => {
      requestedUrl = input;
      requestedInit = init;
      return new Response(JSON.stringify({
        ...detail,
        generationId: 'generation/v1',
        profile: { ...detail.profile, generationId: 'generation/v1' },
        evidence: { ...detail.evidence, generationId: 'generation/v1' },
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }, 'http://backend.test');

    expect(result.kind).toBe('published');
    expect(requestedUrl).toBe(
      'http://backend.test/api/v1/rardar/projects/1211139949?generationId=generation%2Fv1',
    );
    expect(requestedInit).toMatchObject({
      cache: 'force-cache',
      next: { revalidate: 5 },
      headers: { Accept: 'application/json' },
    });
  });

  it.each([
    [404, { detail: { code: 'rardar_project_not_found' } }, { kind: 'not_found' }],
    [409, { detail: { code: 'rardar_serving_source_not_found' } }, { kind: 'revision_mismatch' }],
    [500, { detail: { code: 'rardar_serving_hash_mismatch' } }, { kind: 'error', code: 'rardar_serving_hash_mismatch' }],
    [500, null, { kind: 'error', code: 'rardar_project_unavailable' }],
  ])('maps detail response status %s without guessing another project', async (status, payload, expected) => {
    const result = await loadProjectDetail(1, 'generation-v1', async () => new Response(
      JSON.stringify(payload),
      { status, headers: { 'content-type': 'application/json' } },
    ));
    expect(result).toEqual(expected);
  });

  it('fails closed when the detail request cannot be decoded', async () => {
    const result = await loadProjectDetail(1, 'generation-v1', async () => {
      throw new Error('network unavailable');
    });
    expect(result).toEqual({ kind: 'error', code: 'rardar_project_unavailable' });
  });

  it('rejects malformed detail structures before rendering', () => {
    expect(() => parseProjectDetail(null)).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({ ...detail, project: { ...detail.project, githubRepositoryId: 0 } })).toThrow(
      'rardar_project_response_invalid',
    );
    expect(() => parseProjectDetail({
      ...detail,
      evidence: { ...detail.evidence, githubRepositoryId: 7 },
    })).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, officialSummaryZh: null },
    })).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, startHere: null },
    })).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, coreValueEvidenceRefs: [7] },
    })).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, officialPositioningZh: rardarAssessmentZh },
    })).toThrow('rardar_project_response_invalid');
    expect(() => parseProjectDetail({
      ...detail,
      profile: { ...detail.profile, officialNarrativePromptVersion: null },
    })).toThrow('rardar_project_response_invalid');
  });

  it('keeps a partial profile useful without inventing an unsupported use-case section', () => {
    const partial = {
      ...detail,
      profile: {
        ...detail.profile,
        profileState: 'partial' as const,
        qualityState: 'partial' as const,
        qualityIssues: ['core_value_missing'],
        primaryUseCasesZh: [],
      },
    };
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={partial} />);
    expect(html).toContain('档案部分可用');
    expect(html).not.toContain('适合解决什么');
    expect(html).toContain('打开 GitHub');
  });

  it('keeps a rejected detail useful while hiding every rejected semantic claim', () => {
    const rejected = {
      ...detail,
      profile: {
        ...detail.profile,
        officialSummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
        identitySummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
        coreValueZh: null,
        coreValueEvidenceRefs: [],
        keyDifferentiators: [],
        capabilities: [],
        capabilityBulletsZh: [],
        productFormsZh: [],
        supportedEnvironmentsZh: [],
        deliveryFormsZh: [],
        qualityState: 'rejected' as const,
        qualityIssues: ['identity_source_rejected'],
        sourceLabel: '受限概括' as const,
        officialTaglineZh: null,
        officialTaglineEvidenceRefs: [],
        officialPositioningZh: null,
        officialPositioningEvidenceRefs: [],
        positioningZh: null,
        positioningSourceMode: 'insufficient' as const,
        positioningEvidenceRefs: [],
        positioningIncludedRoles: [],
        positioningExcludedClauses: [],
        officialHighlights: [],
        officialNarrativeMode: 'insufficient' as const,
        officialNarrativeIssues: ['official_narrative_insufficient' as const],
        rardarAssessmentZh: null,
        rardarAssessmentEvidenceRefs: [],
        rardarDifferentiators: [],
      },
    };
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={rejected} />);

    expect(html).toContain('低质量内容已隔离');
    expect(html).toContain('官方核心定位仍在补证');
    expect(html).not.toContain('它能做什么');
    expect(html).not.toContain('确定性中间表示');
    expect(html).toContain('打开 GitHub');
  });
});
