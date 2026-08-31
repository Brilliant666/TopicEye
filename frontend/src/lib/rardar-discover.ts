import {
  assertPublishableProject,
  type ProjectCapability,
  type ProjectDetail,
} from './rardar-intelligence';

export type DiscoverStage = 'just_discovered' | 'rising' | 'near_validation';
export type DiscoverStatus = 'ready' | 'empty' | 'stale' | 'not_configured' | 'invalid';
export type DiscoverCategory = 'ai-agent' | 'dev-tools' | 'data-infra' | 'productivity' | 'video-content' | 'other';
export type DiscoverCategorySource = 'canonical_profile' | 'github_metadata' | 'deterministic_fallback';
export type DiscoverSignalFact =
  | 'first_seen_recently'
  | 'continuous_positive_growth'
  | 'absolute_growth_gate'
  | 'relative_growth_gate'
  | 'awaiting_today_settlement';

export type DiscoverItem = {
  githubRepositoryId: number;
  repository: string;
  url: string;
  stage: DiscoverStage;
  firstSeenAt: string;
  lastObservedAt: string;
  observedWindowStart: string;
  observedWindowEnd: string;
  observedWindowHours: number;
  observedStarDelta: number;
  totalStars: number;
  captureCount: number;
  consecutiveCaptureCount: number;
  language: string | null;
  topics: string[];
  license: string | null;
  isFork: boolean;
  isArchived: boolean;
  isDisabled: false;
  latestPushAt: string;
  sourceCaptureIds: string[];
  sourceEvidenceDigest: string;
  relativeGrowthPercent?: number | null;
  positiveIntervalCount?: number | null;
  consecutivePositiveIntervalCount?: number | null;
  latestIntervalDelta?: number | null;
  publishReasonCodes?: DiscoverSignalFact[] | null;
  signalFacts?: DiscoverSignalFact[] | null;
};

export type DiscoverCard = DiscoverItem & {
  identitySummaryZh: string;
  positioningZh: string;
  capabilities: ProjectCapability[];
  sourceMode: 'official_zh' | 'official_translated' | 'rardar_derived';
  qualityState: 'ready' | 'partial';
  category?: DiscoverCategory | null;
  categorySourceMode?: DiscoverCategorySource | null;
  categoryEvidenceRefs?: string[];
};

export type DiscoverSuppressionSummary = {
  candidateCount: number;
  stageEligibleCount: number;
  publishedCount: number;
  suppressedWeakSignalCount: number;
  suppressedExactCount: number;
  conflictCount: number;
  reasons: {
    weak_absolute_growth: number;
    weak_relative_growth: number;
    no_continuous_growth: number;
    already_in_today: number;
    identity_conflict: number;
    negative_growth: number;
    disabled: number;
    metadata_incomplete: number;
  };
};

export type DiscoverCoverage = {
  state: 'healthy' | 'degraded';
  querySuccessCount: number;
  queryFailureCount: number;
  metadataFailureCount: number;
  sourceCaptureCount: number;
  candidateCount: number;
  publishedCount: number;
  conflictCount: number;
  excludedExactCount: number;
};

export type DiscoverResponse = {
  status: DiscoverStatus;
  generation: string | null;
  generatedAt: string | null;
  latestCaptureId: string | null;
  latestCaptureAt: string | null;
  nextExpectedAt: string | null;
  freshnessState: 'fresh' | 'stale' | 'unavailable';
  updateCadenceMinutes: 120;
  stageCounts: { justDiscovered: number; rising: number; nearValidation: number };
  stages: {
    justDiscovered: DiscoverCard[];
    rising: DiscoverCard[];
    nearValidation: DiscoverCard[];
  };
  coverage: DiscoverCoverage | null;
  conflicts: { count: number; reasons: Record<string, number> };
  todayExplosionGenerationId: string | null;
  sourceWindowStart: string | null;
  sourceWindowEnd: string | null;
  sourceCaptureCount: number;
  profileSummary: {
    selectedCount: number;
    identityComplete: number;
    positioningComplete: number;
    capabilitiesComplete: number;
    categoryComplete?: number;
    officialZh: number;
    officialTranslated: number;
    rardarDerived: number;
    githubRequests: number;
    readmeCacheHits: number;
    translationCalls: number;
    translationCacheHits: number;
  } | null;
  sourceSchemaVersion?: 1 | 2 | null;
  sourcePolicyVersion?: 'trending-discover-v1' | 'trending-discover-v2' | null;
  suppressionSummary?: DiscoverSuppressionSummary | null;
  code: string | null;
};

export type DiscoverProjectDetail = {
  schemaVersion: 1 | 2;
  servingGenerationId: string;
  discoverGenerationId: string;
  facts: DiscoverItem;
  profile: ProjectDetail['profile'];
  evidence: ProjectDetail['evidence'];
  coverage: DiscoverCoverage;
  conflictCount: number;
  category?: DiscoverCategory | null;
  categorySourceMode?: DiscoverCategorySource | null;
  categoryEvidenceRefs?: string[];
  nextExpectedAt?: string | null;
  nextTodaySettlementAt?: string | null;
  todayStatus?: 'not_in_source_today' | null;
  todayReason?: 'new_candidate' | 'awaiting_growth_evidence' | 'awaiting_daily_settlement' | null;
};

export type DiscoverLoadResult =
  | { kind: 'published'; board: DiscoverResponse }
  | { kind: 'not_configured'; code: string }
  | { kind: 'invalid'; code: string };

export type DiscoverDetailLoadResult =
  | { kind: 'published'; detail: DiscoverProjectDetail }
  | { kind: 'not_found' }
  | { kind: 'revision_mismatch' }
  | { kind: 'error'; code: string };

type FetchLike = typeof fetch;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

const SIGNAL_FACTS = new Set<DiscoverSignalFact>([
  'first_seen_recently',
  'continuous_positive_growth',
  'absolute_growth_gate',
  'relative_growth_gate',
  'awaiting_today_settlement',
]);
const CATEGORIES = new Set<DiscoverCategory>([
  'ai-agent', 'dev-tools', 'data-infra', 'productivity', 'video-content', 'other',
]);
const CATEGORY_SOURCES = new Set<DiscoverCategorySource>([
  'canonical_profile', 'github_metadata', 'deterministic_fallback',
]);

function optionalFinite(value: unknown, minimum?: number): boolean {
  return value === undefined || value === null
    || (typeof value === 'number' && Number.isFinite(value) && (minimum === undefined || value >= minimum));
}

function optionalInteger(value: unknown, minimum?: number): boolean {
  return value === undefined || value === null
    || (integer(value) && (minimum === undefined || value >= minimum));
}

function optionalSignalFacts(value: unknown): value is DiscoverSignalFact[] | null | undefined {
  return value === undefined || value === null
    || (Array.isArray(value) && value.length > 0 && value.every((item) => SIGNAL_FACTS.has(item as DiscoverSignalFact)));
}

function capability(value: unknown): value is ProjectCapability {
  return record(value)
    && typeof value.title === 'string'
    && typeof value.detail === 'string'
    && (value.shortDetail === null || typeof value.shortDetail === 'string')
    && strings(value.evidenceRefs)
    && ['official_zh', 'official_translated', 'rardar_derived', 'deterministic_fallback'].includes(
      String(value.sourceMode),
    );
}

function discoverItem(value: unknown): value is DiscoverItem {
  if (!record(value)) return false;
  return integer(value.githubRepositoryId)
    && value.githubRepositoryId > 0
    && typeof value.repository === 'string'
    && typeof value.url === 'string'
    && ['just_discovered', 'rising', 'near_validation'].includes(String(value.stage))
    && typeof value.firstSeenAt === 'string'
    && typeof value.lastObservedAt === 'string'
    && typeof value.observedWindowStart === 'string'
    && typeof value.observedWindowEnd === 'string'
    && typeof value.observedWindowHours === 'number'
    && Number.isFinite(value.observedWindowHours)
    && integer(value.observedStarDelta)
    && value.observedStarDelta >= 0
    && integer(value.totalStars)
    && value.totalStars >= 0
    && integer(value.captureCount)
    && integer(value.consecutiveCaptureCount)
    && (value.language === null || typeof value.language === 'string')
    && strings(value.topics)
    && (value.license === null || typeof value.license === 'string')
    && typeof value.isFork === 'boolean'
    && typeof value.isArchived === 'boolean'
    && value.isDisabled === false
    && typeof value.latestPushAt === 'string'
    && strings(value.sourceCaptureIds)
    && typeof value.sourceEvidenceDigest === 'string'
    && optionalFinite(value.relativeGrowthPercent, 0)
    && optionalInteger(value.positiveIntervalCount, 0)
    && optionalInteger(value.consecutivePositiveIntervalCount, 0)
    && optionalInteger(value.latestIntervalDelta)
    && optionalSignalFacts(value.publishReasonCodes)
    && optionalSignalFacts(value.signalFacts)
    && (
      value.publishReasonCodes === undefined
      || value.publishReasonCodes === null
      || value.signalFacts === undefined
      || value.signalFacts === null
      || JSON.stringify(value.publishReasonCodes) === JSON.stringify(value.signalFacts)
    );
}

function discoverCard(value: unknown): value is DiscoverCard {
  if (!discoverItem(value) || !record(value)) return false;
  const enriched: Record<string, unknown> = value;
  return typeof enriched.identitySummaryZh === 'string'
    && enriched.identitySummaryZh.length > 1
    && typeof enriched.positioningZh === 'string'
    && enriched.positioningZh.length > 1
    && Array.isArray(enriched.capabilities)
    && enriched.capabilities.length > 0
    && enriched.capabilities.every(capability)
    && ['official_zh', 'official_translated', 'rardar_derived'].includes(String(enriched.sourceMode))
    && ['ready', 'partial'].includes(String(enriched.qualityState))
    && (
      enriched.category === undefined
      || enriched.category === null
      || (
        CATEGORIES.has(enriched.category as DiscoverCategory)
        && CATEGORY_SOURCES.has(enriched.categorySourceMode as DiscoverCategorySource)
        && strings(enriched.categoryEvidenceRefs)
        && enriched.categoryEvidenceRefs.length > 0
      )
    );
}

function parseSuppression(value: unknown): DiscoverSuppressionSummary {
  if (!record(value) || !record(value.reasons)) throw new Error('rardar_discover_response_invalid');
  const reasons = value.reasons;
  const fields = [
    'candidateCount', 'stageEligibleCount', 'publishedCount', 'suppressedWeakSignalCount',
    'suppressedExactCount', 'conflictCount',
  ];
  const reasonFields = [
    'weak_absolute_growth', 'weak_relative_growth', 'no_continuous_growth', 'already_in_today',
    'identity_conflict', 'negative_growth', 'disabled', 'metadata_incomplete',
  ];
  if (fields.some((key) => !integer(value[key]) || Number(value[key]) < 0)
    || reasonFields.some((key) => !integer(reasons[key]) || Number(reasons[key]) < 0)) {
    throw new Error('rardar_discover_response_invalid');
  }
  return value as DiscoverSuppressionSummary;
}

function parseCoverage(value: unknown): DiscoverCoverage {
  if (!record(value)
    || !['healthy', 'degraded'].includes(String(value.state))
    || !integer(value.querySuccessCount)
    || !integer(value.queryFailureCount)
    || !integer(value.metadataFailureCount)
    || !integer(value.sourceCaptureCount)
    || !integer(value.candidateCount)
    || !integer(value.publishedCount)
    || !integer(value.conflictCount)
    || !integer(value.excludedExactCount)) {
    throw new Error('rardar_discover_response_invalid');
  }
  return value as DiscoverCoverage;
}

export function parseDiscoverResponse(value: unknown): DiscoverResponse {
  if (!record(value)
    || !['ready', 'empty', 'stale', 'not_configured', 'invalid'].includes(String(value.status))
    || !['fresh', 'stale', 'unavailable'].includes(String(value.freshnessState))
    || value.updateCadenceMinutes !== 120
    || !record(value.stageCounts)
    || !integer(value.stageCounts.justDiscovered)
    || !integer(value.stageCounts.rising)
    || !integer(value.stageCounts.nearValidation)
    || !record(value.stages)
    || !Array.isArray(value.stages.justDiscovered)
    || !Array.isArray(value.stages.rising)
    || !Array.isArray(value.stages.nearValidation)
    || !value.stages.justDiscovered.every(discoverCard)
    || !value.stages.rising.every(discoverCard)
    || !value.stages.nearValidation.every(discoverCard)
    || value.stages.justDiscovered.some((item) => item.stage !== 'just_discovered')
    || value.stages.rising.some((item) => item.stage !== 'rising')
    || value.stages.nearValidation.some((item) => item.stage !== 'near_validation')) {
    throw new Error('rardar_discover_response_invalid');
  }
  const values = [
    ...value.stages.justDiscovered,
    ...value.stages.rising,
    ...value.stages.nearValidation,
  ] as DiscoverCard[];
  if (new Set(values.map((item) => item.githubRepositoryId)).size !== values.length) {
    throw new Error('rardar_discover_response_invalid');
  }
  if (['ready', 'empty', 'stale'].includes(String(value.status))) {
    if (typeof value.generation !== 'string'
      || typeof value.latestCaptureId !== 'string'
      || typeof value.latestCaptureAt !== 'string'
      || typeof value.nextExpectedAt !== 'string'
      || value.coverage === null
      || !record(value.profileSummary)
      || !integer(value.profileSummary.selectedCount)
      || value.profileSummary.selectedCount !== values.length
      || (value.profileSummary.categoryComplete !== undefined
        && (!integer(value.profileSummary.categoryComplete)
          || value.profileSummary.categoryComplete !== values.length))
      || value.stageCounts.justDiscovered < value.stages.justDiscovered.length
      || value.stageCounts.rising < value.stages.rising.length
      || value.stageCounts.nearValidation < value.stages.nearValidation.length) {
      throw new Error('rardar_discover_response_invalid');
    }
    parseCoverage(value.coverage);
  }
  if (value.sourceSchemaVersion !== undefined && value.sourceSchemaVersion !== null
    && ![1, 2].includes(Number(value.sourceSchemaVersion))) {
    throw new Error('rardar_discover_response_invalid');
  }
  if (value.sourcePolicyVersion !== undefined && value.sourcePolicyVersion !== null
    && !['trending-discover-v1', 'trending-discover-v2'].includes(String(value.sourcePolicyVersion))) {
    throw new Error('rardar_discover_response_invalid');
  }
  if (value.suppressionSummary !== undefined && value.suppressionSummary !== null) {
    parseSuppression(value.suppressionSummary);
  }
  if ((value.sourceSchemaVersion === 2 || value.sourcePolicyVersion === 'trending-discover-v2')
    && (value.sourceSchemaVersion !== 2
      || value.sourcePolicyVersion !== 'trending-discover-v2'
      || value.suppressionSummary === undefined
      || value.suppressionSummary === null)) {
    throw new Error('rardar_discover_response_invalid');
  }
  return value as unknown as DiscoverResponse;
}

export async function loadDiscover(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<DiscoverLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/discover`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    const payload: unknown = await response.json();
    const parsed = parseDiscoverResponse(payload);
    if (response.ok && ['ready', 'empty', 'stale'].includes(parsed.status)) {
      return { kind: 'published', board: parsed };
    }
    if (parsed.status === 'not_configured') {
      return { kind: 'not_configured', code: parsed.code || 'rardar_discover_not_configured' };
    }
    return { kind: 'invalid', code: parsed.code || 'rardar_discover_invalid' };
  } catch {
    return { kind: 'invalid', code: 'rardar_discover_unavailable' };
  }
}

export function parseDiscoverProjectDetail(value: unknown): DiscoverProjectDetail {
  if (!record(value)
    || ![1, 2].includes(Number(value.schemaVersion))
    || typeof value.servingGenerationId !== 'string'
    || typeof value.discoverGenerationId !== 'string'
    || !discoverItem(value.facts)
    || !record(value.profile)
    || !record(value.evidence)
    || value.profile.githubRepositoryId !== value.facts.githubRepositoryId
    || value.evidence.githubRepositoryId !== value.facts.githubRepositoryId
    || value.profile.repository !== value.facts.repository
    || value.evidence.repository !== value.facts.repository
    || value.profile.generationId !== value.discoverGenerationId
    || value.evidence.generationId !== value.discoverGenerationId
    || (value.schemaVersion === 2 && (
      !CATEGORIES.has(value.category as DiscoverCategory)
      || !CATEGORY_SOURCES.has(value.categorySourceMode as DiscoverCategorySource)
      || !strings(value.categoryEvidenceRefs)
      || value.categoryEvidenceRefs.length === 0
      || typeof value.nextExpectedAt !== 'string'
      || typeof value.nextTodaySettlementAt !== 'string'
      || value.todayStatus !== 'not_in_source_today'
      || !['new_candidate', 'awaiting_growth_evidence', 'awaiting_daily_settlement'].includes(
        String(value.todayReason),
      )
    ))) {
    throw new Error('rardar_discover_project_invalid');
  }
  assertPublishableProject(value.profile, true);
  parseCoverage(value.coverage);
  return value as unknown as DiscoverProjectDetail;
}

export async function loadDiscoverProjectDetail(
  githubRepositoryId: number,
  generationId: string,
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<DiscoverDetailLoadResult> {
  try {
    const response = await fetcher(
      `${backendUrl}/api/v1/rardar/discover/projects/${githubRepositoryId}?generationId=${encodeURIComponent(generationId)}`,
      {
        cache: 'force-cache',
        headers: { Accept: 'application/json' },
      },
    );
    const payload: unknown = await response.json();
    if (response.ok) return { kind: 'published', detail: parseDiscoverProjectDetail(payload) };
    const detail = record(payload) && record(payload.detail) ? payload.detail : null;
    const code = detail && typeof detail.code === 'string' ? detail.code : 'rardar_discover_project_unavailable';
    if (response.status === 404) return { kind: 'not_found' };
    if (response.status === 409) return { kind: 'revision_mismatch' };
    return { kind: 'error', code };
  } catch {
    return { kind: 'error', code: 'rardar_discover_project_unavailable' };
  }
}
