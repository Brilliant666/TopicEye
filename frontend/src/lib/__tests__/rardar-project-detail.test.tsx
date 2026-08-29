import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { loadProjectDetail, parseProjectDetail, type ProjectDetail } from '@/lib/rardar-intelligence';

const detail: ProjectDetail = {
  schemaVersion: 3,
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
    officialSummaryZh: '根据代码仓库生成可交互架构图，并保留路径证据。',
    sourceLabel: '官方 README（译）',
    sourceLanguage: 'en',
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
    translationState: 'translated',
  },
  profile: {
    profileSchemaVersion: 'rardar-project-profile-v3',
    promptVersion: 'rardar-project-profile-zh-v4',
    githubRepositoryId: 1211139949,
    repository: 'tt-a1i/archify',
    htmlUrl: 'https://github.com/tt-a1i/archify',
    generationId: 'generation-v1',
    profileState: 'complete',
    officialSummaryZh: '根据代码仓库生成可交互架构图，并保留路径证据。',
    sourceLabel: '官方 README（译）',
    sourceLanguage: 'en',
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
    claimEvidenceRefs: { '根据代码仓库生成可交互架构图，并保留路径证据。': ['readme:section:1'] },
    readmePath: 'README.md',
    readmeBlobSha: 'a'.repeat(40),
    selectedSections: [{
      heading: 'Overview', path: 'README.md#overview', purpose: 'overview',
      excerpts: ['Generate interactive architecture diagrams.'], listItems: [], evidenceRefs: ['readme:section:1'],
    }],
    originalExcerpts: ['Generate interactive architecture diagrams.'],
    startHere: [{
      label: 'README · Overview', path: 'README.md#overview',
      htmlUrl: 'https://github.com/tt-a1i/archify/blob/main/README.md#overview', evidenceRefs: ['readme:section:1'],
    }],
    evidenceDigest: 'b'.repeat(64),
    generatedAt: '2026-08-28T01:00:00Z',
    translationState: 'translated',
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
  it('renders an immutable official profile, Today facts, and the two on-demand actions', () => {
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={detail} />);

    expect(html).toContain('tt-a1i/archify');
    expect(html).toContain('根据代码仓库生成可交互架构图');
    expect(html).toContain('生成独立 HTML / SVG 架构图');
    expect(html).toContain('技术图与交互展示');
    expect(html).toContain('架构变化对比');
    expect(html).toContain('可追溯架构探索');
    expect(html).toContain('Agent Skill');
    expect(html).toContain('Claude Code');
    expect(html).toContain('独立 HTML');
    expect(html).toContain('今日为什么出现在这里');
    expect(html).toContain('+5,246');
    expect(html).toContain('README.md#overview');
    expect(html).toContain('查看官方原文与版本来源');
    expect(html).toContain('1 个 metadata failure');
    expect(html).toContain('14 个负增长冲突');
    expect(html).toContain('生成 AI 深度解读');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ftt-a1i%2Farchify');
    expect(html).not.toContain('稳定性仍需验证');
    expect(html).toContain('官方 README · 2处证据');
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
  });

  it('keeps a partial profile useful without inventing an unsupported use-case section', () => {
    const partial = {
      ...detail,
      profile: { ...detail.profile, profileState: 'partial' as const, primaryUseCasesZh: [] },
    };
    const html = renderToStaticMarkup(<RardarProjectDetailPage detail={partial} />);
    expect(html).toContain('档案部分可用');
    expect(html).not.toContain('适合解决什么');
    expect(html).toContain('打开 GitHub');
  });
});
