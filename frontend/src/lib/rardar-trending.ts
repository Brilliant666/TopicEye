import type { ProjectDetail } from './rardar-intelligence';

export type BoardSource = {
  source: 'github' | 'trendshift'; label: string; status: 'healthy' | 'stale' | 'failed';
  sourceDate: string | null; fetchedAt: string | null; errorCode: string | null; count: number;
};
export type BoardAppearance = {
  source: 'github' | 'trendshift'; rank: number; sourceDate: string | null;
  fetchedAt: string; captureDate?: string; period: string;
  reportedDelta: number | null; reportedDeltaPeriod?: string | null;
  trendshiftStarsGained?: number | null; trendshiftStarsGainedLabel?: string | null;
  trendshiftMetricPeriod?: string | null;
  sourceStatus?: 'healthy' | 'stale' | 'failed'; totalStars?: number | null;
};
export type TrendingProject = {
  projectId: string; repository: string; repositoryUrl: string; githubRepositoryId: number | null;
  description: string | null; totalStars: number | null; dualListed: boolean;
  appearances: BoardAppearance[];
  primaryGrowth?: (Omit<Partial<BoardAppearance>, 'source'> & { source: 'github' | 'trendshift' | 'rardar_history'; value: number; windowStartedAt?: string; windowEndedAt?: string }) | null;
  displayRank?: number;
  historicalContext?: { kind: 'board' | 'rardar' | 'reported_count'; source: string; rank?: number; dateKind?: 'source' | 'capture' | 'window'; date?: string; fetchedAt?: string; reportedAppearanceCount?: number } | null;
  totalStarsSource?: { source: 'github' | 'trendshift'; sourceDate: string | null; fetchedAt: string; status: 'healthy' | 'stale' | 'failed' } | null;
  materialState: 'complete' | 'partial' | 'unavailable';
  displayProfile?: ProjectDetail['profile'] | null;
  displayEvidence?: ProjectDetail['evidence'] | null;
  material?: { schemaVersion: 2; sourceKind: 'profile_cache' | 'published_serving'; sourceGeneration: string; sourceRevision: string; generatedAt: string } | null;
  language?: string | null; topics?: string[]; license?: string | null;
  metadataSource?: { fetchedAt: string; sourceUrl: string };
  productForms?: string[]; runtimeEnvironments?: string[]; artifactTypes?: string[];
  profile: null | { summary: string; positioning: string; capabilities: string[]; generatedAt: string; sourceUrl: string; sourceLabel?: string; useCases?: string[]; limitations?: string[] | null; startHere?: Array<{ label: string; url: string }> };
  historyAppearances?: number; firstSeenAt?: string | null; lastSeenAt?: string | null;
  historicalEvidence?: Array<{ source: string; sourceUrl: string; reportedAppearanceCount: number; sourceDate: string | null; fetchedAt: string }>;
  historicalRardarEvidence?: Array<{ source: 'rardar_today'; sourceGeneration: string; servingGeneration: string; rank: number; windowStartedAt: string; windowEndedAt: string; observedStarDelta: number; totalStars: number }>;
};
export type TrendingBoard = { schemaVersion: number; metricSchemaVersion?: 2; generationId: string; publishedAt: string | null; checkedAt: string | null; sources: BoardSource[]; projects: TrendingProject[] };
export type TrendingDetail = TrendingProject & { metricSchemaVersion?: 2; generationId?: string; publishedAt?: string | null; sources?: BoardSource[] };

export function projectLink(projectId: string, generationId: string, historical = false) {
  return `/project/stable/${encodeURIComponent(projectId)}?${historical ? 'history=1' : `generation=${encodeURIComponent(generationId)}`}`;
}
export function safeSourceUrl(value: string): string | undefined {
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : undefined; } catch { return undefined; }
}
export async function loadTrending<T>(path: string, fetcher: typeof fetch = fetch): Promise<T | null> {
  try {
    const response = await fetcher(`${process.env.BACKEND_API_URL || 'http://127.0.0.1:8102'}/api/v1/rardar/${path}`, { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) return null;
    return await response.json() as T;
  } catch { return null; }
}
export function boardTime(value: string | null | undefined) {
  if (!value) return '日期未知';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '日期未知';
}

/** History may contain several captures; selection is independent of array order. */
export function latestBoardAppearances(appearances: BoardAppearance[]): BoardAppearance[] {
  return (['github', 'trendshift'] as const).flatMap(source => {
    const rows = appearances.filter(item => item.source === source).sort((a, b) => {
      const aTime = Date.parse(a.fetchedAt); const bTime = Date.parse(b.fetchedAt);
      const time = (Number.isFinite(bTime) ? bTime : -Infinity) - (Number.isFinite(aTime) ? aTime : -Infinity);
      return (Number.isNaN(time) ? 0 : time) || JSON.stringify(a).localeCompare(JSON.stringify(b));
    });
    return rows.length ? [rows[0]] : [];
  });
}
