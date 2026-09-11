export type ProjectExplanation = {
  state: 'ready' | 'unavailable';
  repository: string;
  githubRepositoryId: number | null;
  generationId: string;
  promptVersion: 'rardar-project-insight-v5';
  schemaVersion: 'rardar-project-insight-schema-v5';
  format: 'structured' | 'none';
  officialIntro: EvidenceBackedIntro;
  analysis: {
    conclusionSummary: EvidenceBackedText;
    differentiators: EvidenceBackedText[];
    reusableAssets: Array<{
      reuseType: ReuseType;
      asset: string;
      howToUse: string;
      evidenceRefs: string[];
    }>;
    reuseCost: {
      level: 'low' | 'medium' | 'high' | 'unknown';
      reason: string;
      evidenceRefs: string[];
    };
    bestFitScenarios: EvidenceBackedText[];
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
  isProvided: boolean;
  evidenceState: 'ready' | 'metadata_only' | 'not_analyzed';
};

export type FindProjectResponse = {
  requirement: string;
  repositoryUrl: string | null;
  searchState: 'github_live' | 'limited' | 'demo';
  coverageLabel: string;
  sources: string[];
  requirementProfile: { purpose: string; mustHave: string[]; preferences: string[]; exclusions: string[]; queries: string[] };
  queriedQueries: string[];
  evidenceSources: Array<{ repository: string; ref: string; url: string; text: string; kind: string }>;
  quickCandidates: QuickProjectCandidate[];
  aiState: 'ready' | 'plain' | 'unavailable' | 'insufficient_candidates';
  comparison: {
    candidates: Array<{
      repository: string;
      whatItDoes: string;
      whyMatched: string;
      reusableParts: string[];
      integrationCost: 'low' | 'medium' | 'high' | 'unknown';
      requirementChecks: Array<{ requirement: string; status: 'supported' | 'not_supported' | 'unknown'; reason: string; evidenceRefs: string[]; supportingQuote?: string }>;
      evidenceRefs: string[];
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

async function postJson<T>(path: string, body: unknown, loginError?: string): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && loginError) throw new Error(loginError);
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

export function explainProjectById(githubRepositoryId: number, generationId: string) {
  return postJson<ProjectExplanation>(`/api/v1/rardar/projects/${githubRepositoryId}/insight`, { generationId });
}

export function explainDiscoverProjectById(githubRepositoryId: number, generationId: string) {
  return postJson<ProjectExplanation>(`/api/v1/rardar/discover/projects/${githubRepositoryId}/insight`, { generationId });
}

export type SharedProjectInsightStatus = {
  state: 'unprocessed' | 'running' | 'ready' | 'waiting' | 'unavailable';
  result: ProjectExplanation | null;
  errorCode: string | null;
};

export type SharedProjectContext = 'trending' | 'historical_hot';

export async function readSharedProjectInsight(projectId: string, generationId: string, context: SharedProjectContext) {
  const query = new URLSearchParams({ generationId, context });
  const response = await fetch(`/api/v1/rardar/project-insights/${encodeURIComponent(projectId)}?${query}`, {
    cache: 'no-store', headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error('project_insight_read_failed');
  return await response.json() as SharedProjectInsightStatus;
}

export function explainSharedProject(projectId: string, generationId: string, context: SharedProjectContext) {
  return postJson<SharedProjectInsightStatus>(`/api/v1/rardar/project-insights/${encodeURIComponent(projectId)}`, {
    generationId, context,
  }, 'project_insight_login_required');
}

export function findProjects(requirement: string, repositoryUrl: string | null) {
  return postJson<FindProjectResponse>('/api/v1/rardar/find-projects', { requirement, repositoryUrl });
}
