export interface EvidenceRef {
  kind: string;
  label: string;
  url?: string | null;
  observedAt: string;
}

export interface ExplosionProject {
  rank: number;
  projectId: string;
  githubRepositoryId: number;
  repository: string;
  summaryZh: string;
  coreCapabilities: string[];
  aiStatus: 'pending' | 'ready' | 'failed';
  observedStarDelta: number;
  totalStars: number;
  forks: number;
  pushedAt: string;
  windowStartedAt: string;
  windowEndedAt: string;
  sourceProvenance: EvidenceRef[];
  ai: {
    state: string;
    profile: null | {
      whyTrendingHypothesis: string;
      coreCapabilities: string[];
      confidence: number;
      limitations: string[];
    };
    label?: string;
    errorCode?: string;
  };
}

export interface ExplosionBoard {
  productProfile: string;
  generationId: string;
  artifactVersion: 1;
  artifactRevision: string;
  capturedAt: string;
  publishedAt: string;
  rankingContract: string;
  aiChangesRanking: false;
  exactTop: ExplosionProject[];
  firstSeenPending: Array<{
    projectId: string;
    repository: string;
    summaryZh: string;
    firstSeenAt: string;
    observedWindowHours: number;
    observedWindowStarDelta: number;
    totalStars: number;
    externalSignals: string[];
    aiStatus: 'pending' | 'ready' | 'failed';
    sourceProvenance: EvidenceRef[];
  }>;
  coverageState: 'healthy' | 'degraded';
  sourceSummary: string;
  coverage: {
    candidateSources: string[];
    successfulQueries: number;
    recalledCandidates: number;
    observedRepositories: number;
    degradedSources: string[];
    statement: string;
  };
}

const serverApiBase = () =>
  `${process.env.BACKEND_API_URL || 'http://127.0.0.1:8102'}/api/v1`;

export async function fetchExplosionBoard(): Promise<ExplosionBoard> {
  const response = await fetch(`${serverApiBase()}/rardar/explosion-board`, {
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`explosion_board_${response.status}`);
  return response.json() as Promise<ExplosionBoard>;
}

export async function rardarRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/rardar${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.code || `request_${response.status}`);
  }
  return body as T;
}
