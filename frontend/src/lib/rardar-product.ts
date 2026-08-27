export type ProjectExplanation = {
  state: 'ready' | 'unavailable';
  repository: string;
  generationId: string;
  promptVersion: 'rardar-project-insight-v2';
  schemaVersion: 'rardar-project-insight-schema-v2';
  format: 'structured' | 'none';
  officialIntro: EvidenceBackedIntro;
  analysis: {
    officialIntro: EvidenceBackedIntro;
    coreHighlights: EvidenceBackedText[];
    reusableAssets: Array<{
      reuseType: ReuseType;
      asset: string;
      howToUse: string;
      evidenceRefs: string[];
    }>;
    startHere: Array<{ label: string; path: string; evidenceRefs: string[] }>;
    implementationBoundaries: EvidenceBackedText[];
  } | null;
  errorCode: string | null;
  model: string | null;
  provider: string | null;
  cacheHit: boolean;
  evidenceDigest: string;
  evidenceCacheHit: boolean;
  evidenceKinds: string[];
};

type EvidenceBackedText = { text: string; evidenceRefs: string[] };
type EvidenceBackedIntro = EvidenceBackedText & {
  sourceLabel: '官方介绍' | '官方介绍（译）' | 'AI受限概括';
};

export type ReuseType =
  | 'whole_product'
  | 'module_library'
  | 'provider_connector'
  | 'workflow'
  | 'reference_only'
  | 'not_recommended';

export const REUSE_TYPE_LABELS: Record<ReuseType, string> = {
  whole_product: '整套产品复用',
  module_library: '模块 / 类库复用',
  provider_connector: 'Provider / 连接器',
  workflow: '工作流复用',
  reference_only: '仅供参考',
  not_recommended: '不建议复用',
};

export type QuickProjectCandidate = {
  githubRepositoryId: number;
  repository: string;
  description: string | null;
  totalStars: number;
  updatedAt: string;
  primaryLanguage: string | null;
  licenseSpdxId: string | null;
  topics: string[];
  htmlUrl: string;
  preliminaryMatch: string;
  dataState: 'github_live' | 'local_demo';
};

export type FindProjectResponse = {
  requirement: string;
  repositoryUrl: string | null;
  searchState: 'github_live' | 'limited' | 'demo';
  coverageLabel: string;
  sources: string[];
  quickCandidates: QuickProjectCandidate[];
  aiState: 'ready' | 'plain' | 'unavailable' | 'insufficient_candidates';
  comparison: {
    candidates: Array<{
      repository: string;
      whatItDoes: string;
      whyMatched: string;
      reusableParts: string[];
      integrationCost: 'low' | 'medium' | 'high';
      risks: string[];
      recommendation: string;
      reuseType: ReuseType;
    }>;
    overallConclusion: string;
  } | null;
  plainComparison: string | null;
  errorCode: string | null;
  model: string | null;
  provider: string | null;
  cacheHit: boolean;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const code = isRecord(payload) && isRecord(payload.detail) && typeof payload.detail.code === 'string'
      ? payload.detail.code
      : 'rardar_request_failed';
    throw new Error(code);
  }
  return payload as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function explainProject(repository: string, generationId: string) {
  return postJson<ProjectExplanation>('/api/v1/rardar/projects/explain', { repository, generationId });
}

export function findProjects(requirement: string, repositoryUrl: string | null) {
  return postJson<FindProjectResponse>('/api/v1/rardar/find-projects', { requirement, repositoryUrl });
}
