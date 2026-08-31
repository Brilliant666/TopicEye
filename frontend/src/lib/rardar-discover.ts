import {
  assertPublishableProject,
  type ProjectCapability,
  type ProjectDetail,
} from './rardar-intelligence';

export type DiscoverStage = 'just_discovered' | 'outside_today_momentum' | 'rising' | 'near_validation';
export type DiscoverStatus = 'ready' | 'empty' | 'stale' | 'not_configured' | 'invalid';
export type DiscoverCategory = 'ai-agent' | 'dev-tools' | 'data-infra' | 'productivity' | 'video-content' | 'other';
export type DiscoverCategorySource = 'canonical_profile' | 'github_metadata' | 'deterministic_fallback';
export type DiscoverSignalFact =
  | 'first_seen_recently'
  | 'outside_today_top20'
  | 'exact_rank_available'
  | 'recent_absolute_growth'
  | 'recent_relative_growth'
  | 'continuous_recent_growth'
  | 'recent_acceleration'
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
  eligibilityClass?: 'pre_exact' | 'exact_outside_published' | null;
  todayExactRank?: number | null;
  todayExact24hDelta?: number | null;
  recentWindowHours?: number | null;
  recentObservedStarDelta?: number | null;
  priorComparableWindowDelta?: number | null;
  accelerationDelta?: number | null;
  recentRelativeGrowthPercent?: number | null;
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

export type DiscoverSuppressionSummaryV3 = {
  candidateCount: number;
  publishedCount: number;
  suppressedSignalCount: number;
  excludedPublishedCount: number;
  conflictCount: number;
  reasons: {
    today_published: number;
    weak_recent_absolute_growth: number;
    weak_recent_relative_growth: number;
    no_recent_continuous_growth: number;
    no_recent_acceleration: number;
    weak_pre_exact_growth: number;
    already_exact_without_momentum: number;
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
  excludedExactCount?: number | null;
  todayExactCount?: number | null;
  todayPublishedCount?: number | null;
  excludedPublishedCount?: number | null;
  exactOutsidePublishedEvaluatedCount?: number | null;
  preExactEvaluatedCount?: number | null;
  invalidCount?: number | null;
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
  stageCounts: { justDiscovered: number; outsideTodayMomentum: number; rising: number; nearValidation: number };
  stages: {
    justDiscovered: DiscoverCard[];
    outsideTodayMomentum: DiscoverCard[];
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
  sourceSchemaVersion?: 1 | 2 | 3 | null;
  sourcePolicyVersion?: 'trending-discover-v1' | 'trending-discover-v2' | 'trending-discover-v3' | null;
  suppressionSummary?: DiscoverSuppressionSummary | DiscoverSuppressionSummaryV3 | null;
  todayPublishedTopCount?: 20 | null;
  eligibilitySummary?: {
    observationCandidates: number;
    todayExactFacts: number;
    todayPublished: number;
    excludedPublished: number;
    exactOutsidePublishedEvaluated: number;
    preExactEvaluated: number;
    invalid: number;
    published: number;
    suppressed: number;
  } | null;
  code: string | null;
};

export type DiscoverProjectDetail = {
  schemaVersion: 1 | 2 | 3;
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
  todayStatus?: 'not_in_source_today' | 'outside_today_top20' | null;
  todayReason?: 'new_candidate' | 'awaiting_growth_evidence' | 'awaiting_daily_settlement' | 'outside_today_top20_with_momentum' | null;
  todayPublishedTopCount?: 20 | null;
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
  'outside_today_top20',
  'exact_rank_available',
  'recent_absolute_growth',
  'recent_relative_growth',
  'continuous_recent_growth',
  'recent_acceleration',
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
    && ['just_discovered', 'outside_today_momentum', 'rising', 'near_validation'].includes(String(value.stage))
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
    && (value.eligibilityClass === undefined
      || value.eligibilityClass === null
      || ['pre_exact', 'exact_outside_published'].includes(String(value.eligibilityClass)))
    && optionalInteger(value.todayExactRank, 21)
    && optionalInteger(value.todayExact24hDelta, 0)
    && optionalFinite(value.recentWindowHours, 0)
    && optionalInteger(value.recentObservedStarDelta)
    && optionalInteger(value.priorComparableWindowDelta)
    && optionalInteger(value.accelerationDelta)
    && optionalFinite(value.recentRelativeGrowthPercent)
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

function parseSuppression(value: unknown): DiscoverSuppressionSummary | DiscoverSuppressionSummaryV3 {
  if (!record(value) || !record(value.reasons)) throw new Error('rardar_discover_response_invalid');
  const reasons = value.reasons;
  const v2Fields = [
    'candidateCount', 'stageEligibleCount', 'publishedCount', 'suppressedWeakSignalCount',
    'suppressedExactCount', 'conflictCount',
  ];
  const v2ReasonFields = [
    'weak_absolute_growth', 'weak_relative_growth', 'no_continuous_growth', 'already_in_today',
    'identity_conflict', 'negative_growth', 'disabled', 'metadata_incomplete',
  ];
  if (v2Fields.every((key) => integer(value[key]) && Number(value[key]) >= 0)
    && v2ReasonFields.every((key) => integer(reasons[key]) && Number(reasons[key]) >= 0)) {
    return value as DiscoverSuppressionSummary;
  }
  const v3Fields = [
    'candidateCount', 'publishedCount', 'suppressedSignalCount', 'excludedPublishedCount', 'conflictCount',
  ];
  const v3ReasonFields = [
    'today_published', 'weak_recent_absolute_growth', 'weak_recent_relative_growth',
    'no_recent_continuous_growth', 'no_recent_acceleration', 'weak_pre_exact_growth',
    'already_exact_without_momentum', 'identity_conflict', 'negative_growth', 'disabled',
    'metadata_incomplete',
  ];
  if (v3Fields.every((key) => integer(value[key]) && Number(value[key]) >= 0)
    && v3ReasonFields.every((key) => integer(reasons[key]) && Number(reasons[key]) >= 0)) {
    return value as DiscoverSuppressionSummaryV3;
  }
  throw new Error('rardar_discover_response_invalid');
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
    || !optionalInteger(value.excludedExactCount, 0)
    || !optionalInteger(value.todayExactCount, 0)
    || !optionalInteger(value.todayPublishedCount, 0)
    || !optionalInteger(value.excludedPublishedCount, 0)
    || !optionalInteger(value.exactOutsidePublishedEvaluatedCount, 0)
    || !optionalInteger(value.preExactEvaluatedCount, 0)
    || !optionalInteger(value.invalidCount, 0)) {
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
    || !integer(value.stageCounts.outsideTodayMomentum)
    || !integer(value.stageCounts.rising)
    || !integer(value.stageCounts.nearValidation)
    || !record(value.stages)
    || !Array.isArray(value.stages.justDiscovered)
    || !Array.isArray(value.stages.outsideTodayMomentum)
    || !Array.isArray(value.stages.rising)
    || !Array.isArray(value.stages.nearValidation)
    || !value.stages.justDiscovered.every(discoverCard)
    || !value.stages.outsideTodayMomentum.every(discoverCard)
    || !value.stages.rising.every(discoverCard)
    || !value.stages.nearValidation.every(discoverCard)
    || value.stages.justDiscovered.some((item) => item.stage !== 'just_discovered')
    || value.stages.outsideTodayMomentum.some((item) => item.stage !== 'outside_today_momentum')
    || value.stages.rising.some((item) => item.stage !== 'rising')
    || value.stages.nearValidation.some((item) => item.stage !== 'near_validation')) {
    throw new Error('rardar_discover_response_invalid');
  }
  const values = [
    ...value.stages.justDiscovered,
    ...value.stages.outsideTodayMomentum,
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
      || value.stageCounts.outsideTodayMomentum < value.stages.outsideTodayMomentum.length
      || value.stageCounts.rising < value.stages.rising.length
      || value.stageCounts.nearValidation < value.stages.nearValidation.length) {
      throw new Error('rardar_discover_response_invalid');
    }
    parseCoverage(value.coverage);
  }
  if (value.sourceSchemaVersion !== undefined && value.sourceSchemaVersion !== null
    && ![1, 2, 3].includes(Number(value.sourceSchemaVersion))) {
    throw new Error('rardar_discover_response_invalid');
  }
  if (value.sourcePolicyVersion !== undefined && value.sourcePolicyVersion !== null
    && !['trending-discover-v1', 'trending-discover-v2', 'trending-discover-v3'].includes(String(value.sourcePolicyVersion))) {
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
  if (value.sourceSchemaVersion === 3 || value.sourcePolicyVersion === 'trending-discover-v3') {
    const summary = value.eligibilitySummary;
    const v3Items = values;
    const fields = [
      'observationCandidates', 'todayExactFacts', 'todayPublished', 'excludedPublished',
      'exactOutsidePublishedEvaluated', 'preExactEvaluated', 'invalid', 'published', 'suppressed',
    ];
    if (value.sourceSchemaVersion !== 3
      || value.sourcePolicyVersion !== 'trending-discover-v3'
      || value.suppressionSummary === undefined
      || value.suppressionSummary === null
      || !record(value.suppressionSummary)
      || !('suppressedSignalCount' in value.suppressionSummary)
      || value.todayPublishedTopCount !== 20
      || !record(summary)
      || !record(value.coverage)
      || fields.some((key) => !integer(summary[key]) || Number(summary[key]) < 0)
      || summary.observationCandidates !== value.coverage.candidateCount
      || summary.todayExactFacts !== value.coverage.todayExactCount
      || summary.todayPublished !== value.coverage.todayPublishedCount
      || summary.excludedPublished !== value.coverage.excludedPublishedCount
      || summary.exactOutsidePublishedEvaluated !== value.coverage.exactOutsidePublishedEvaluatedCount
      || summary.preExactEvaluated !== value.coverage.preExactEvaluatedCount
      || summary.invalid !== value.coverage.invalidCount
      || summary.published !== value.coverage.publishedCount
      || summary.suppressed !== value.suppressionSummary.suppressedSignalCount
      || v3Items.some((item) => (
        !['pre_exact', 'exact_outside_published'].includes(String(item.eligibilityClass))
        || typeof item.recentWindowHours !== 'number'
        || !Number.isFinite(item.recentWindowHours)
        || !Array.isArray(item.publishReasonCodes)
        || !Array.isArray(item.signalFacts)
      ))
      || v3Items.filter((item) => item.stage !== 'outside_today_momentum').some((item) => (
        item.eligibilityClass !== 'pre_exact'
        || item.todayExactRank !== null
        || item.todayExact24hDelta !== null
      ))
      || value.stages.outsideTodayMomentum.some((item) => (
        item.eligibilityClass !== 'exact_outside_published'
        || !integer(item.todayExactRank)
        || Number(item.todayExactRank) <= 20
        || !integer(item.todayExact24hDelta)
        || !integer(item.recentObservedStarDelta)
        || !integer(item.priorComparableWindowDelta)
        || !integer(item.accelerationDelta)
      ))) {
      throw new Error('rardar_discover_response_invalid');
    }
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
    || ![1, 2, 3].includes(Number(value.schemaVersion))
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
    || ([2, 3].includes(Number(value.schemaVersion)) && (
      !CATEGORIES.has(value.category as DiscoverCategory)
      || !CATEGORY_SOURCES.has(value.categorySourceMode as DiscoverCategorySource)
      || !strings(value.categoryEvidenceRefs)
      || value.categoryEvidenceRefs.length === 0
      || typeof value.nextExpectedAt !== 'string'
      || typeof value.nextTodaySettlementAt !== 'string'
      || !['not_in_source_today', 'outside_today_top20'].includes(String(value.todayStatus))
      || ![
        'new_candidate', 'awaiting_growth_evidence', 'awaiting_daily_settlement',
        'outside_today_top20_with_momentum',
      ].includes(
        String(value.todayReason),
      )
    ))
    || (value.schemaVersion === 3 && (
      value.todayPublishedTopCount !== 20
      || (value.facts.stage === 'outside_today_momentum') !== (value.facts.eligibilityClass === 'exact_outside_published')
      || (value.facts.stage === 'outside_today_momentum' && (
        value.todayStatus !== 'outside_today_top20'
        || value.todayReason !== 'outside_today_top20_with_momentum'
        || !integer(value.facts.todayExactRank)
        || Number(value.facts.todayExactRank) <= 20
        || !integer(value.facts.todayExact24hDelta)
        || !integer(value.facts.recentObservedStarDelta)
        || !integer(value.facts.priorComparableWindowDelta)
        || !integer(value.facts.accelerationDelta)
      ))
      || (value.facts.stage !== 'outside_today_momentum' && (
        value.facts.eligibilityClass !== 'pre_exact'
        || value.todayStatus !== 'not_in_source_today'
        || value.facts.todayExactRank !== null
        || value.facts.todayExact24hDelta !== null
      ))
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
