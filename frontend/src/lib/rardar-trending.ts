export type BoardSource = {
  source: 'github' | 'trendshift'; label: string; status: 'healthy' | 'stale' | 'failed';
  sourceDate: string | null; fetchedAt: string | null; errorCode: string | null; count: number;
};
export type TrendingProject = {
  projectId: string; repository: string; repositoryUrl: string; githubRepositoryId: number | null;
  description: string | null; totalStars: number | null; dualListed: boolean;
  appearances: Array<{ source: 'github' | 'trendshift'; rank: number; sourceDate: string | null; fetchedAt: string; period: string; reportedDelta: number | null }>;
  materialState: 'complete' | 'partial' | 'unavailable';
  profile: null | { summary: string; positioning: string; capabilities: string[]; generatedAt: string; sourceUrl: string; sourceLabel?: string; useCases?: string[]; limitations?: string[]; startHere?: Array<{ label: string; url: string }> };
  historyAppearances?: number; firstSeenAt?: string | null; lastSeenAt?: string | null;
  historicalEvidence?: Array<{ source: string; sourceUrl: string; reportedAppearanceCount: number; sourceDate: string | null; fetchedAt: string }>;
};
export type TrendingBoard = { schemaVersion: number; generationId: string; publishedAt: string | null; checkedAt: string | null; sources: BoardSource[]; projects: TrendingProject[] };
export type TrendingDetail = TrendingProject & { generationId?: string; publishedAt?: string | null; sources?: BoardSource[] };

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
