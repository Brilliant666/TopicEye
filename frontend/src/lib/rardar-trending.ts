import type { ProjectDetail } from './rardar-intelligence';

export type BoardPeriod = {
  periodStartAt?: string | null; periodEndAt?: string | null; sourceTimezone?: string | null;
  acquisitionMode?: 'ended_utc_day' | 'daily_snapshot'; targetPeriodDate?: string | null;
};
export type RefreshPolicy = {
  timezone: 'Asia/Shanghai'; readinessMinutes: number; compensationDelayMinutes: number;
  timingBasis: string;
  duePeriod: { sourceDate: string; startAt: string; endAt: string; readyAt: string };
  schedule: Array<{ runDate: string; mainAt: string; compensationAt: string; targetSourceDate: string; periodStartAt: string; periodEndAt: string }>;
};
export type BoardSource = BoardPeriod & {
  source: 'github' | 'trendshift'; label: string; status: 'healthy' | 'stale' | 'failed';
  sourceDate: string | null; fetchedAt: string | null; errorCode: string | null; count: number;
  checkedAt?: string | null;
};
export type BoardAppearance = BoardPeriod & {
  source: 'github' | 'trendshift'; rank: number; sourceDate: string | null;
  githubRepositoryId?: number | null;
  fetchedAt: string; captureDate?: string; period: string;
  reportedDelta: number | null; reportedDeltaPeriod?: string | null;
  trendshiftStarsGained?: number | null; trendshiftStarsGainedLabel?: string | null;
  trendshiftMetricPeriod?: string | null;
  sourceStatus?: 'healthy' | 'stale' | 'failed'; totalStars?: number | null;
};
/** Validated reading fields needed by a list card; full evidence stays on detail. */
export type TrendingCardNarrative = Pick<ProjectDetail['profile'],
  'officialTaglineZh' | 'identitySummaryZh' | 'officialSummaryZh' | 'coreValueZh'
  | 'positioningZh' | 'productFormsZh' | 'officialNarrativeMode' | 'positioningSourceMode'>;
export type TrendingProject = {
  projectId: string; repository: string; repositoryUrl: string; githubRepositoryId: number | null;
  identityState?: 'needs_identity_evidence'; identityRepositoryIds?: number[];
  description: string | null; totalStars: number | null; dualListed: boolean;
  appearances: BoardAppearance[];
  primaryGrowth?: (Omit<Partial<BoardAppearance>, 'source'> & { source: 'github' | 'trendshift' | 'rardar_history'; value: number; windowStartedAt?: string; windowEndedAt?: string }) | null;
  displayRank?: number;
  historicalContext?: { kind: 'board' | 'rardar' | 'reported_count'; source: string; rank?: number; dateKind?: 'source' | 'capture' | 'window'; date?: string; fetchedAt?: string; reportedAppearanceCount?: number } | null;
  totalStarsSource?: { source: 'github' | 'trendshift' | 'github_metadata' | 'rardar_history'; sourceDate: string | null; fetchedAt: string | null; status: 'healthy' | 'stale' | 'failed' | 'saved'; sourceUrl?: string; observedAt?: string | null; timeKind?: 'observed' | 'source_date' | 'unknown'; historicalSaved?: boolean } | null;
  materialState: 'complete' | 'partial' | 'unavailable';
  materialAttempt?: { status: string; stage?: 'source' | 'translation' | 'profile' | null; errorCode?: string | null; checkedAt?: string | null; nextAction?: string | null; reason?: string | null; nextAllowedAt?: string | null } | null;
  displayCard?: TrendingCardNarrative | null;
  displayProfile?: (Omit<ProjectDetail['profile'], 'generatedAt'> & { generatedAt: string | null }) | null;
  displayEvidence?: ProjectDetail['evidence'] | null;
  material?: { schemaVersion: 2; sourceKind: 'profile_cache' | 'published_serving' | 'partial_introduction' | 'partial_profile'; sourceGeneration: string; sourceRevision: string; generatedAt: string | null; savedAt?: string; sourceState?: 'changed' | 'unchanged'; sourceCheckedAt?: string | null } | null;
  language?: string | null; topics?: string[]; license?: string | null;
  metadataSource?: { fetchedAt: string; sourceUrl: string };
  productForms?: string[]; runtimeEnvironments?: string[]; artifactTypes?: string[];
  profile: null | { summary: string; positioning: string | null; capabilities?: string[]; generatedAt: string | null; savedAt?: string; sourceUrl: string; sourceLabel?: string; summaryEvidence?: Array<{ ref: string; text: string; url: string }>; useCases?: string[]; limitations?: string[] | null; startHere?: Array<{ label: string; url: string }> };
  historyAppearances?: number | null; firstSeenAt?: string | null; lastSeenAt?: string | null;
  historicalEvidence?: Array<{ source: string; sourceUrl: string; reportedAppearanceCount: number; sourceDate: string | null; fetchedAt: string }>;
  historicalRardarEvidence?: Array<{ source: 'rardar_today'; sourceGeneration: string; servingGeneration: string; rank: number; windowStartedAt: string; windowEndedAt: string; observedStarDelta?: number; totalStars: number }>;
};
export type DailyHistoryReview = {
  date: string; publishedAt: string; projectIds: string[]; candidateCount: number;
  relaxedRecentWindow: boolean; limit: number; lookbackDays: number; trigger: string;
};
export type TrendingBoard = {
  schemaVersion: number; metricSchemaVersion?: 2; generationId: string | null;
  readingRevision?: string;
  publishedAt: string | null; checkedAt: string | null; sources: BoardSource[];
  projects: TrendingProject[]; refreshPolicy?: RefreshPolicy;
  rawProjectCount?: number; eligibleProjectCount?: number; unknownGrowthCount?: number;
  minimumDailyGrowth?: number; dailyReview?: DailyHistoryReview | null;
  state?: string;
};
export type TrendingDetail = TrendingProject & { metricSchemaVersion?: 2; generationId?: string; readingRevision?: string; publishedAt?: string | null; sources?: BoardSource[] };

export function projectLink(projectId: string, generationId: string, historical = false, readingRevision?: string) {
  return `/project/stable/${encodeURIComponent(projectId)}?${historical ? 'history=1' : `generation=${encodeURIComponent(generationId)}`}${readingRevision ? `&readingRevision=${encodeURIComponent(readingRevision)}` : ''}`;
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

export type PublishedBoardView = 'trending-today' | 'historical-hot';

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const text = (value: unknown) => value == null || typeof value === 'string';
const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value);
const scalar = (value: unknown) => value == null || ['string', 'number', 'boolean'].includes(typeof value);
const textList = (value: unknown) => value == null || (Array.isArray(value) && value.every(item => typeof item === 'string'));
const optionalObject = (value: unknown, validate: (item: Record<string, unknown>) => boolean) => value == null || (record(value) && validate(value));
const optionalRows = (value: unknown, validate: (item: Record<string, unknown>) => boolean) => value == null || (Array.isArray(value) && value.every(item => record(item) && validate(item)));

function validReadingProject(project: unknown, historical: boolean): boolean {
  if (!record(project) || typeof project.projectId !== 'string' || typeof project.repository !== 'string'
    || ![project.description, project.language, project.license].every(text)
    || ![project.topics, project.productForms].every(textList)
    || !Array.isArray(project.appearances)
    || !project.appearances.every(appearance => record(appearance)
      && text(appearance.source) && scalar(appearance.rank)
      && [appearance.sourceDate, appearance.fetchedAt, appearance.reportedDeltaPeriod, appearance.trendshiftMetricPeriod].every(text))) return false;

  const narrative = (value: unknown) => optionalObject(value, item => [
    item.officialTaglineZh, item.identitySummaryZh, item.officialSummaryZh,
    item.coreValueZh, item.positioningZh, item.officialNarrativeMode, item.positioningSourceMode,
  ].every(text) && textList(item.productFormsZh));
  return narrative(project.displayCard) && narrative(project.displayProfile)
    && optionalObject(project.profile, item => [item.summary, item.positioning, item.sourceLabel].every(text))
    && (historical || optionalObject(project.primaryGrowth, item => finite(item.value)))
    && optionalObject(project.material, item => [item.sourceState, item.sourceCheckedAt].every(text))
    && optionalObject(project.metadataSource, item => text(item.fetchedAt))
    && optionalObject(project.historicalContext, item => [item.kind, item.source, item.date].every(text))
    && optionalObject(project.totalStarsSource, item => [item.sourceDate, item.fetchedAt, item.observedAt].every(text))
    && optionalRows(project.historicalEvidence, item => text(item.sourceUrl) && scalar(item.reportedAppearanceCount))
    && optionalRows(project.historicalRardarEvidence, item => text(item.sourceGeneration)
      && scalar(item.rank) && [item.windowStartedAt, item.windowEndedAt].every(text));
}

function validPublishedBoard(value: unknown, revision: string, view: PublishedBoardView): value is TrendingBoard {
  if (!record(value) || value.readingRevision !== revision
    || ![value.publishedAt, value.checkedAt].every(text)
    || !Array.isArray(value.projects) || !Array.isArray(value.sources)) return false;
  const emptyHistory = view === 'historical-hot' && value.projects.length === 0
    && (value.state === 'pending_daily_review' || (value.state === 'ready' && record(value.dailyReview)));
  if (typeof value.generationId !== 'string' && !(value.generationId === null && emptyHistory)) return false;

  // The publisher validates the complete saved document. Check the reading
  // boundary here as well so a malformed response cannot become a partial list.
  return value.projects.every(project => validReadingProject(project, view === 'historical-hot'))
    && value.sources.every(source => record(source)
      && [source.source, source.sourceDate, source.fetchedAt, source.checkedAt].every(text)
      && scalar(source.label) && scalar(source.count))
    && optionalObject(value.dailyReview, item => text(item.date) && text(item.publishedAt)
      && scalar(item.lookbackDays))
    && optionalObject(value.refreshPolicy, item => record(item.duePeriod)
      && text(item.duePeriod.sourceDate) && scalar(item.readinessMinutes));
}

/** Cache only immutable, public reading artifacts; never identity or Find data. */
export async function loadPublishedBoard(
  view: PublishedBoardView,
  fetcher: typeof fetch = fetch,
): Promise<TrendingBoard | null> {
  if (view !== 'trending-today' && view !== 'historical-hot') return null;
  const base = `${process.env.BACKEND_API_URL || 'http://127.0.0.1:8102'}/api/v1/rardar/public-reading`;
  try {
    // A publication change selects a new immutable URL. Do not cache this pointer
    // or rely on a timed frontend rebuild to discover a newly published board.
    const pointerResponse = await fetcher(base, {
      cache: 'no-store', headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15000),
    });
    if (!pointerResponse.ok) return null;
    const pointer: unknown = await pointerResponse.json();
    if (!record(pointer) || pointer.schemaVersion !== 1 || !record(pointer.views)) return null;
    const publication = pointer.views[view];
    if (!record(publication) || typeof publication.revision !== 'string'
      || !/^[a-f0-9]{64}$/.test(publication.revision)
      || typeof publication.publishedAt !== 'string' || !Number.isFinite(Date.parse(publication.publishedAt))
      || !(publication.generationId === null || typeof publication.generationId === 'string')) return null;

    const response = await fetcher(`${base}/${view}/${publication.revision}`, {
      cache: 'force-cache', headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) return null;
    const board: unknown = await response.json();
    if (!validPublishedBoard(board, publication.revision, view)
      || board.generationId !== publication.generationId) return null;
    return board;
  } catch { return null; }
}

export function boardTime(value: string | null | undefined) {
  if (!value) return '日期未知';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '日期未知';
}

export function totalStarsProvenance(source: TrendingProject['totalStarsSource']) {
  if (!source) return '来源与数据时间未取得';
  const label = { github: 'GitHub Trending', trendshift: 'Trendshift', github_metadata: 'GitHub 仓库元数据', rardar_history: 'Rardar 历史观测' }[source.source];
  const time = source.observedAt ? `数据读取 ${beijingTime(source.observedAt)}` : source.sourceDate ? `来源数据日期 ${source.sourceDate}` : '数据时间未知';
  return `${label} · ${source.historicalSaved ? '历史保存值 · ' : ''}${time} · 本地采集 ${beijingTime(source.fetchedAt)}`;
}

/** The saved Star observation is independent of the day's review publication. */
export function totalStarsDataTime(source: TrendingProject['totalStarsSource']) {
  if (source?.observedAt) return `数据读取 ${beijingTime(source.observedAt)}`;
  if (source?.sourceDate) return `来源数据日期 ${boardTime(source.sourceDate)}`;
  if (source?.fetchedAt) return `采集时间 ${beijingTime(source.fetchedAt)} · 数据时间未知`;
  return '数据时间未知';
}

export function introductionUnavailableText(project: TrendingProject) {
  return project.materialAttempt?.status === 'failed' && project.materialAttempt.stage === 'source'
    ? '资料读取失败，暂时保留上榜信息。'
    : '暂未取得可用的项目介绍，仓库与榜单事实仍可查看。';
}

/** A reused repository name cannot establish continuity between different IDs. */
export function identityEvidenceNotice(project: TrendingProject) {
  return project.identityState === 'needs_identity_evidence'
    ? '仓库身份尚待核实，暂不合并资料与 Star；请按原来源核对。'
    : null;
}

/** A checked source revision is distinct from the saved interpretation's age. */
export function materialSourceNotice(project: TrendingProject) {
  if (project.material?.sourceState !== 'changed') return null;
  return project.displayCard || project.displayProfile || project.profile
    ? '来源内容已更新，当前展示已保存资料；等待后续更新。'
    : '来源内容已更新，项目资料待补充。';
}

/** Only timezone-aware instants are rendered; source calendar dates are not instants. */
export function beijingTime(value: string | null | undefined) {
  if (!value || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value))) return '时间未知';
  return `${boardTime(value)} 北京时间`;
}

export function boardPeriodLabel(source: BoardPeriod & { sourceDate: string | null }) {
  if (source.acquisitionMode === 'ended_utc_day' && source.periodStartAt && source.periodEndAt) {
    return `已结束 UTC 日 ${source.sourceDate ?? '日期未知'} · ${beijingTime(source.periodStartAt)} → ${beijingTime(source.periodEndAt)}（右端不含）`;
  }
  const date = source.sourceDate ? `源榜日期 ${source.sourceDate}${source.sourceTimezone ? `（${source.sourceTimezone}）` : '（源时区未记录）'} · ` : '源榜日期未知 · ';
  return `${date}${source.acquisitionMode === 'daily_snapshot' ? '日榜快照' : '已保存日榜记录'}，未确认完整统计窗口`;
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
