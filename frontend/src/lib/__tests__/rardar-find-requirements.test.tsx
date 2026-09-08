import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ClientLayout from '@/components/ClientLayout';
import RardarFindProjectPage, { FindResults, validSavedFindResults } from '@/components/RardarFindProjectPage';
import type { FindProjectResponse } from '@/lib/rardar-product';
import type { AuthUser } from '@/types';

vi.mock('next/navigation', () => ({ usePathname: () => '/find', useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/product-profile', async (original) => ({ ...await original<typeof import('@/lib/product-profile')>(), activeProductProfile: { rardarEnabled: true } }));
afterEach(() => vi.unstubAllGlobals());

function response(count: number): FindProjectResponse {
  return {
    requirement: '团队文档，必须自托管，不使用 SaaS', repositoryUrl: 'https://github.com/owner/repo-0',
    requirementProfile: { purpose: '团队文档', mustHave: ['自托管'], preferences: [], exclusions: ['SaaS'], queries: ['docs self hosted'] },
    queriedQueries: ['docs self hosted'], searchState: 'github_live', coverageLabel: '有界公开检索', sources: ['GitHub Search'],
    quickCandidates: Array.from({ length: count + 1 }, (_, i) => ({ githubRepositoryId: i + 1, repository: `owner/repo-${i}`, description: '真实元数据', totalStars: 5, updatedAt: '2026-09-08T00:00:00Z', primaryLanguage: null, licenseSpdxId: null, topics: [], htmlUrl: `https://github.com/owner/repo-${i}`, preliminaryMatch: '召回词命中，不是验证', dataState: 'github_live', isProvided: i === 0, evidenceState: i < count ? 'ready' : 'not_analyzed' })),
    evidenceSources: [{ repository: 'owner/repo-0', ref: 'readme', url: 'https://github.com/owner/repo-0/blob/main/README.md', text: 'Self-host on your server', kind: 'README' }],
    aiState: 'ready', comparison: { candidates: Array.from({ length: count }, (_, i) => ({ repository: `owner/repo-${i}`, whatItDoes: '文档工具', whyMatched: '提供自托管说明', reusableParts: [], integrationCost: 'unknown', risks: [], recommendation: '核对部署说明', reuseType: 'whole_product', evidenceRefs: ['readme'], requirementChecks: [{ requirement: '自托管', status: 'supported', reason: 'README 声明可在自己的服务器部署', evidenceRefs: ['readme'] }, { requirement: '免费版权限', status: 'unknown', reason: '缺少版本资料', evidenceRefs: [] }, { requirement: '不依赖 SaaS', status: 'not_supported', reason: '测试中的显式反证', evidenceRefs: ['readme'] }] })), overallConclusion: '须继续核对权限' },
    plainComparison: null, errorCode: null, model: null, provider: null, cacheHit: false,
  };
}

describe('Find requirement-first real component tree', () => {
  it('discards malformed or expired saved results before rendering', () => {
    const expiresAt = Date.now() + 60000;
    expect(validSavedFindResults({ expiresAt, results: [response(1)] })).toBe(true);
    for (const value of [null, {}, { expiresAt: 1, results: [response(1)] }, { expiresAt, results: [{ requirementProfile: {} }] }, { expiresAt, results: [{ ...response(1), evidenceSources: [null] }] }, { expiresAt, results: [{ ...response(1), comparison: { candidates: [null] } }] }, { expiresAt, results: [{ ...response(1), requirementProfile: { ...response(1).requirementProfile, mustHave: null } }] }]) expect(validSavedFindResults(value)).toBe(false);
  });
  it.each([null, { id: 1, role: 'admin' } as AuthUser, { id: 2, role: 'user' } as AuthUser])('renders real Find form through ClientLayout without paid requests for %j', (user) => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const html = renderToStaticMarkup(<ClientLayout initialData={{ user, featureFlags: {}, counts: null }}><RardarFindProjectPage /></ClientLayout>);
    expect(html).toContain('开始找项目'); expect(html).toContain('data-rardar-shell="true"'); expect(fetcher).not.toHaveBeenCalled();
    expect(html).not.toContain('本地演示候选');
  });
  it.each([0, 1, 2, 3])('renders %i analysed candidates without padding', (count) => {
    const html = renderToStaticMarkup(<FindResults result={response(count)} />);
    expect((html.match(/AI 比较 #/g) || []).length).toBe(count);
    expect(html).toContain('团队文档，必须自托管，不使用 SaaS'); expect(html).toContain('尚未深入分析');
    expect(html).not.toContain('不足 3');
    if (count === 0) expect(html).toContain('没有找到足够依据');
    else { expect(html).toContain('资料支持'); expect(html).toContain('尚未确认'); expect(html).toContain('资料表明不满足'); expect(html).toContain('https://github.com/owner/repo-0/blob/main/README.md'); expect(html).toContain('未知，需实际验证'); expect(html).toContain('你提供的仓库'); }
  });
  it('keeps real candidates readable on model failure without exposing unvalidated plain output', () => {
    const data = response(1); data.aiState = 'unavailable'; data.comparison = null; data.plainComparison = 'unverified model prose';
    const html = renderToStaticMarkup(<FindResults result={data} />);
    expect(html).toContain('owner/repo-0'); expect(html).toContain('目前没有足够依据'); expect(html).not.toContain('unverified model prose');
  });
});
