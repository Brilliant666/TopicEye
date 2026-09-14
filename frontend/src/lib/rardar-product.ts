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
  requirementProfile: { purpose: string; mustHave: string[]; preferences: string[]; exclusions: string[]; queries: string[] } | null;
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

async function postJson<T>(path: string, body: unknown, loginError?: string, extraHeaders: Record<string, string> = {}): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...extraHeaders },
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

/** @deprecated Use submitFindRun to obtain the durable ID before execution. Persist this key before calling; recover via readFindRunByKey after response loss. */
export function findProjects(requirement: string, repositoryUrl: string | null, idempotencyKey: string) {
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(idempotencyKey || '')) throw new Error('find_idempotency_key_invalid');
  return postJson<FindProjectResponse>('/api/v1/rardar/find-projects', { requirement, repositoryUrl }, '请先登录', { 'Idempotency-Key': idempotencyKey });
}

export type FindRunStatus = 'created' | 'running' | 'completed' | 'no_candidates' | 'partial' | 'failed' | 'budget_stopped' | 'interrupted' | 'uncertain';
export type FindRun = {
  runId: string; status: FindRunStatus; stage: string; createdAt: string; updatedAt: string;
  finishedAt: string | null; request: { requirement: string; repositoryUrl: string | null };
  result: FindProjectResponse | null; errorCode: string | null; requestLimit: number;
  requestsUsed: number; schemaVersion: 'rardar-find-run-v1';
};
export type FindRunSummary = Pick<FindRun, 'runId' | 'status' | 'stage' | 'createdAt' | 'updatedAt' | 'requestsUsed'> & {
  requirementSummary: string; repositoryUrl: string | null;
};

async function findRunRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/rardar/find-runs${path}`, {
    ...options, cache: 'no-store', credentials: 'same-origin',
    headers: { Accept: 'application/json', ...options.headers },
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error('请先登录后查看或保存 Find 结果');
    if (response.status === 404) throw new Error('尚未找到此运行记录，或当前账号无权访问');
    if (response.status === 409) throw new Error('同一提交标识与原需求不一致，请回查原运行');
    throw new Error('服务器暂未确认运行状态，请回查，不要重复提交');
  }
  return await response.json() as T;
}

export const readFindRun = (id: string) => findRunRequest<FindRun>(`/${encodeURIComponent(id)}`);
export const readFindRunByKey = (key: string) => findRunRequest<FindRun>(`/by-key/${encodeURIComponent(key)}`);
export const listFindRuns = () => findRunRequest<{ runs: FindRunSummary[] }>('');
export async function executeFindRun(id: string): Promise<FindRun> {
  try { return await findRunRequest<FindRun>(`/${encodeURIComponent(id)}/execute`, { method: 'POST' }); }
  catch { return readFindRun(id); } // A lost response is not permission to repeat paid work.
}
export async function submitFindRun(request: FindRun['request'], key: string, created: (run: FindRun) => void | boolean): Promise<FindRun> {
  let run: FindRun;
  try {
    run = await findRunRequest<FindRun>('', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(request),
    });
  } catch {
    run = await readFindRunByKey(key);
    created(run);
    return run; // Creation response was lost: only recover; explicit action can execute a created run.
  }
  if (created(run) === false) return run; // Account/session changed while creation was in flight.
  return run.status === 'created' ? executeFindRun(run.runId) : run;
}
