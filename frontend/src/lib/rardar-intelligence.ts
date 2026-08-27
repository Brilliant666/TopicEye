export type ExplosionBoardState = 'ready' | 'warming_up' | 'baseline_missing' | 'not_ready' | 'not_synced';

export interface ExplosionWindow {
  state: 'exact' | 'warming_up' | 'baseline_missing';
  startedAt: string;
  endedAt: string;
  durationHours: 24;
  toleranceSeconds: 600;
}

export interface ExplosionCoverage {
  state: 'healthy' | 'degraded';
  successfulQueryCount: number;
  failedQueryCount: number;
  metadataFailureCount: number;
  exactCount: number;
  pendingCount: number;
  conflictCount: number;
}

export interface ExactExplosionProject {
  rank: number;
  githubRepositoryId: number;
  repository: string;
  htmlUrl: string;
  totalStars: number;
  baselineStars: number;
  observedStarDelta: number;
  windowStartedAt: string;
  windowEndedAt: string;
  primaryLanguage: string | null;
  topics: string[];
  description: string | null;
  forks: number;
  pushedAt: string | null;
  licenseSpdxId: string | null;
  archived: boolean;
  fork: boolean;
  mirrorUrl: string | null;
  state: 'exact_window';
}

export interface PendingExplosionProject {
  pendingRank: number;
  pendingReason: 'first_seen' | 'baseline_missing' | 'baseline_ineligible';
  githubRepositoryId: number;
  repository: string;
  htmlUrl: string;
  totalStars: number;
  firstSeenAt: string;
  observedWindowHours: number | null;
  observedWindowStarDelta: number | null;
  observedWindowStartedAt: string | null;
  observedWindowEndedAt: string | null;
  primaryLanguage: string | null;
  topics: string[];
  description: string | null;
  forks: number;
  pushedAt: string | null;
  licenseSpdxId: string | null;
}

export interface ExplosionBoard {
  state: ExplosionBoardState;
  reason: 'explosion_artifact_not_published' | 'real_data_not_synced' | null;
  generationId: string | null;
  publishedAt: string | null;
  capturedAt: string | null;
  window: ExplosionWindow | null;
  coverage: ExplosionCoverage | null;
  exactRanked: ExactExplosionProject[];
  pendingRanked: PendingExplosionProject[];
  conflictCount: number;
  sourceStatus: {
    currentCaptureId: string;
    baselineCaptureId: string | null;
    partialCaptureCount: number;
    coverageWitnessCaptureId: string | null;
  } | null;
  dataMode: 'real' | 'demo';
  dataLabel: string;
  syncedAt: string | null;
  sourceHost: string | null;
  manifestSha256: string | null;
  artifactSha256: string | null;
}

export type ExplosionBoardLoadResult =
  | { kind: 'published'; board: ExplosionBoard }
  | { kind: 'not_configured' }
  | { kind: 'error'; code: string };

const repositoryPattern = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number.isFinite(value);
}

export function parseExplosionBoard(value: unknown): ExplosionBoard {
  if (!isRecord(value)) throw new Error('rardar_response_invalid');
  const state = value.state;
  if (!['ready', 'warming_up', 'baseline_missing', 'not_ready', 'not_synced'].includes(String(state))) {
    throw new Error('rardar_response_invalid');
  }
  if (
    !((typeof value.generationId === 'string' && typeof value.publishedAt === 'string')
      || (state === 'not_synced' && value.generationId === null && value.publishedAt === null))
  ) {
    throw new Error('rardar_response_invalid');
  }
  if (!Array.isArray(value.exactRanked) || !Array.isArray(value.pendingRanked)) {
    throw new Error('rardar_response_invalid');
  }
  for (const item of value.exactRanked) {
    if (
      !isRecord(item) ||
      !isFiniteInteger(item.rank) ||
      !isFiniteInteger(item.githubRepositoryId) ||
      !isFiniteInteger(item.totalStars) ||
      !isFiniteInteger(item.observedStarDelta) ||
      !isFiniteInteger(item.forks) ||
      typeof item.repository !== 'string' ||
      !repositoryPattern.test(item.repository) ||
      typeof item.htmlUrl !== 'string'
    ) {
      throw new Error('rardar_response_invalid');
    }
  }
  for (const item of value.pendingRanked) {
    if (
      !isRecord(item) ||
      !isFiniteInteger(item.pendingRank) ||
      !isFiniteInteger(item.githubRepositoryId) ||
      !isFiniteInteger(item.totalStars) ||
      !isFiniteInteger(item.forks) ||
      typeof item.repository !== 'string' ||
      !repositoryPattern.test(item.repository) ||
      typeof item.htmlUrl !== 'string'
    ) {
      throw new Error('rardar_response_invalid');
    }
  }
  if (!['real', 'demo'].includes(String(value.dataMode)) || typeof value.dataLabel !== 'string') {
    throw new Error('rardar_response_invalid');
  }
  return value as unknown as ExplosionBoard;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export async function loadExplosionBoard(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<ExplosionBoardLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/explosion-board`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    const payload: unknown = await response.json();
    if (response.ok) return { kind: 'published', board: parseExplosionBoard(payload) };
    const detail = isRecord(payload) && isRecord(payload.detail) ? payload.detail : null;
    const code = detail && typeof detail.code === 'string' ? detail.code : 'rardar_intelligence_unavailable';
    if (response.status === 503 && code === 'rardar_intelligence_not_configured') {
      return { kind: 'not_configured' };
    }
    return { kind: 'error', code };
  } catch {
    return { kind: 'error', code: 'rardar_intelligence_unavailable' };
  }
}
