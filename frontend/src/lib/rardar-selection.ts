export type SelectionStatus = 'ready' | 'empty' | 'degraded' | 'stale' | 'not_configured' | 'invalid';
export type SelectionCategory = 'ai-agent' | 'dev-tools' | 'data-infra' | 'productivity' | 'video-content' | 'other';
export type SelectionReason =
  | 'directly_reusable'
  | 'specific_problem_solution'
  | 'distinctive_implementation'
  | 'reference_or_learning_value';

export type SelectionCard = {
  githubRepositoryId: number;
  repository: string;
  htmlUrl: string;
  identitySummaryZh: string;
  corePositioningZh: string | null;
  whyWorthSeeingZh: string | null;
  whyNowZh: string | null;
  primaryReason: SelectionReason;
  supportingReasons: SelectionReason[];
  category: SelectionCategory;
  categorySource: 'canonical_profile' | 'research_derived';
  productFormsZh: string[];
  primaryLanguage: string | null;
  topics: string[];
  licenseSpdxId: string | null;
  totalStars: number;
  momentumLabel: string | null;
  reusableAssets: string[];
  bestFit: string[];
};

export type SelectionResponse = {
  status: SelectionStatus;
  mode: 'shadow';
  state: SelectionStatus;
  generation: string | null;
  sourceObservation: string | null;
  sourceTodayGeneration: string | null;
  generatedAt: string | null;
  latestCaptureAt: string | null;
  items: SelectionCard[];
  categoryCounts: Record<string, number>;
  primaryReasonCounts: Record<string, number>;
  coverageLabelZh: string | null;
  candidateCount: number;
  selectedCount: number;
  publishedCount: number;
  suppressedCount: number;
  provenance: Record<string, unknown>;
  code: string | null;
  currentGeneration: string | null;
  latestAttemptGeneration: string | null;
  recallCount: number;
  profileReadyCount: number;
  profileReboundCount: number;
  profileRebuiltCount: number;
  retryableFailureCount: number;
  permanentFailureCount: number;
  profileCoverage: number;
  assessmentCoverage: number;
  systemicFailure: boolean;
  safeFailureCodes: string[];
  nextRetryAt: string | null;
  productionReady?: false;
  reviewable?: boolean;
  shadowReviewState?: 'ready' | 'empty' | 'incomplete' | 'invalid' | null;
  shadowReviewGeneration?: string | null;
  candidateUniverseCount?: number;
  healthyProfileCount?: number;
  unresolvedProfileCount?: number;
  cohortSize?: number;
  cohortAssessed?: number;
  previewCount?: number;
  providerBudget?: { limit: number; attempted: number; remaining: number; [key: string]: unknown } | null;
};

export type SelectionEvidence = {
  evidenceId: string;
  sourceType: string;
  sourcePath: string;
  sourceRevision: string;
  excerpt: string;
  githubRepositoryId: number;
};

export type SelectionProjectDetail = {
  selectionGenerationId: string;
  sourceObservationSetId: string;
  context: {
    schemaVersion: 1;
    selectionGenerationId: string;
    sourceObservationSetId: string;
    generatedAt: string;
    card: SelectionCard;
    selectionEvidenceDigest: string;
    timelinessReasonCodes: string[];
    evidence: SelectionEvidence[];
    canonicalProfile: Record<string, unknown>;
    canonicalEvidence: Record<string, unknown>;
  };
};

export type SelectionLoadResult =
  | { kind: 'published'; selection: SelectionResponse }
  | { kind: 'not_configured'; code: string }
  | { kind: 'invalid'; code: string };

export type SelectionDetailLoadResult =
  | { kind: 'published'; detail: SelectionProjectDetail }
  | { kind: 'not_found' }
  | { kind: 'error'; code: string };

type FetchLike = typeof fetch;

const CATEGORIES = new Set<SelectionCategory>([
  'ai-agent', 'dev-tools', 'data-infra', 'productivity', 'video-content', 'other',
]);
const REASONS = new Set<SelectionReason>([
  'directly_reusable', 'specific_problem_solution', 'distinctive_implementation', 'reference_or_learning_value',
]);

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function validGitHubUrl(value: unknown, repository: unknown): value is string {
  if (typeof value !== 'string' || typeof repository !== 'string') return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:'
      && parsed.hostname === 'github.com'
      && parsed.username === ''
      && parsed.password === ''
      && parsed.search === ''
      && parsed.hash === ''
      && parsed.pathname.replace(/\/$/, '') === `/${repository}`;
  } catch {
    return false;
  }
}

export function parseSelectionCard(value: unknown): SelectionCard {
  if (!record(value)
    || !Number.isSafeInteger(value.githubRepositoryId) || Number(value.githubRepositoryId) <= 0
    || typeof value.repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value.repository)
    || !validGitHubUrl(value.htmlUrl, value.repository)
    || typeof value.identitySummaryZh !== 'string' || value.identitySummaryZh.length < 4
    || !nullableString(value.corePositioningZh)
    || (value.whyWorthSeeingZh !== null && (typeof value.whyWorthSeeingZh !== 'string' || value.whyWorthSeeingZh.length < 8))
    || !nullableString(value.whyNowZh)
    || !REASONS.has(value.primaryReason as SelectionReason)
    || !strings(value.supportingReasons) || value.supportingReasons.some((item) => !REASONS.has(item as SelectionReason))
    || !CATEGORIES.has(value.category as SelectionCategory)
    || !['canonical_profile', 'research_derived'].includes(String(value.categorySource))
    || !strings(value.productFormsZh)
    || !nullableString(value.primaryLanguage)
    || !strings(value.topics)
    || !nullableString(value.licenseSpdxId)
    || !Number.isSafeInteger(value.totalStars) || Number(value.totalStars) < 0
    || !nullableString(value.momentumLabel)
    || !strings(value.reusableAssets)
    || !strings(value.bestFit)) {
    throw new Error('rardar_selection_card_invalid');
  }
  return value as SelectionCard;
}

export function parseSelectionResponse(value: unknown): SelectionResponse {
  if (!record(value)
    || value.mode !== 'shadow'
    || !['ready', 'empty', 'degraded', 'stale', 'not_configured', 'invalid'].includes(String(value.status))
    || value.state !== value.status
    || !nullableString(value.generation)
    || !nullableString(value.sourceObservation)
    || !nullableString(value.sourceTodayGeneration)
    || !nullableString(value.generatedAt)
    || !nullableString(value.latestCaptureAt)
    || !Array.isArray(value.items)
    || !record(value.categoryCounts)
    || !record(value.primaryReasonCounts)
    || !nullableString(value.coverageLabelZh)
    || !Number.isSafeInteger(value.candidateCount) || Number(value.candidateCount) < 0
    || !Number.isSafeInteger(value.selectedCount) || Number(value.selectedCount) < 0
    || !Number.isSafeInteger(value.publishedCount) || Number(value.publishedCount) < 0
    || !Number.isSafeInteger(value.suppressedCount) || Number(value.suppressedCount) < 0
    || !record(value.provenance)
    || !nullableString(value.code)
    || !nullableString(value.currentGeneration)
    || !nullableString(value.latestAttemptGeneration)
    || !Number.isSafeInteger(value.recallCount) || Number(value.recallCount) < 0
    || !Number.isSafeInteger(value.profileReadyCount) || Number(value.profileReadyCount) < 0
    || !Number.isSafeInteger(value.profileReboundCount) || Number(value.profileReboundCount) < 0
    || !Number.isSafeInteger(value.profileRebuiltCount) || Number(value.profileRebuiltCount) < 0
    || !Number.isSafeInteger(value.retryableFailureCount) || Number(value.retryableFailureCount) < 0
    || !Number.isSafeInteger(value.permanentFailureCount) || Number(value.permanentFailureCount) < 0
    || typeof value.profileCoverage !== 'number' || value.profileCoverage < 0 || value.profileCoverage > 1
    || typeof value.assessmentCoverage !== 'number' || value.assessmentCoverage < 0 || value.assessmentCoverage > 1
    || typeof value.systemicFailure !== 'boolean'
    || !strings(value.safeFailureCodes)
    || !nullableString(value.nextRetryAt)) {
    throw new Error('rardar_selection_response_invalid');
  }
  const items = value.items.map(parseSelectionCard);
  if (value.shadowReviewState != null) {
    const reviewable = ['ready', 'empty'].includes(String(value.shadowReviewState));
    if (!['ready', 'empty', 'incomplete', 'invalid'].includes(String(value.shadowReviewState))
      || value.productionReady !== false || value.state !== 'degraded'
      || value.currentGeneration !== null || value.generation !== value.shadowReviewGeneration
      || value.cohortSize !== 16 || value.reviewable !== reviewable
      || !Number.isSafeInteger(value.cohortAssessed) || Number(value.cohortAssessed) < 0 || Number(value.cohortAssessed) > 16
      || (reviewable && value.cohortAssessed !== 16)
      || !Number.isSafeInteger(value.healthyProfileCount) || !Number.isSafeInteger(value.unresolvedProfileCount)
      || Number(value.healthyProfileCount) + Number(value.unresolvedProfileCount) !== value.recallCount
      || items.length > 6 || value.previewCount !== items.length
      || (value.shadowReviewState === 'ready') !== (items.length > 0)
      || !record(value.providerBudget) || value.providerBudget.limit !== 40
      || !Number.isSafeInteger(value.providerBudget.attempted) || Number(value.providerBudget.attempted) > 40
      || Number(value.providerBudget.attempted) < 0) {
      throw new Error('rardar_shadow_response_invalid');
    }
  }
  if (items.length > 20
    || new Set(items.map((item) => item.githubRepositoryId)).size !== items.length
    || (value.status === 'ready' && (!value.generation || items.length === 0))
    || (value.status === 'stale' && !value.generation)
    || (value.status === 'empty' && (!value.generation || items.length !== 0))
    || (value.status === 'degraded' && !value.latestAttemptGeneration)) {
    throw new Error('rardar_selection_response_invalid');
  }
  return { ...value, items } as SelectionResponse;
}

export async function loadSelection(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<SelectionLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/discover/selection`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    const parsed = parseSelectionResponse(await response.json());
    if (response.ok && ['ready', 'empty', 'degraded', 'stale'].includes(parsed.status)) {
      return { kind: 'published', selection: parsed };
    }
    if (parsed.status === 'not_configured') {
      return { kind: 'not_configured', code: parsed.code || 'rardar_selection_not_configured' };
    }
    return { kind: 'invalid', code: parsed.code || 'rardar_selection_invalid' };
  } catch {
    return { kind: 'invalid', code: 'rardar_selection_unavailable' };
  }
}

function parseEvidence(value: unknown, repositoryId: number): SelectionEvidence {
  if (!record(value)
    || typeof value.evidenceId !== 'string' || !/^[ETP][0-9]{2}$/.test(value.evidenceId)
    || typeof value.sourceType !== 'string'
    || typeof value.sourcePath !== 'string'
    || typeof value.sourceRevision !== 'string'
    || typeof value.excerpt !== 'string'
    || value.githubRepositoryId !== repositoryId) {
    throw new Error('rardar_selection_detail_invalid');
  }
  return value as SelectionEvidence;
}

export function parseSelectionProjectDetail(value: unknown): SelectionProjectDetail {
  if (!record(value)
    || typeof value.selectionGenerationId !== 'string'
    || typeof value.sourceObservationSetId !== 'string'
    || !record(value.context)
    || value.context.schemaVersion !== 1
    || value.context.selectionGenerationId !== value.selectionGenerationId
    || value.context.sourceObservationSetId !== value.sourceObservationSetId
    || typeof value.context.generatedAt !== 'string'
    || typeof value.context.selectionEvidenceDigest !== 'string'
    || !/^[a-f0-9]{64}$/.test(value.context.selectionEvidenceDigest)
    || !strings(value.context.timelinessReasonCodes)
    || !Array.isArray(value.context.evidence)
    || !record(value.context.canonicalProfile)
    || !record(value.context.canonicalEvidence)) {
    throw new Error('rardar_selection_detail_invalid');
  }
  const card = parseSelectionCard(value.context.card);
  const evidence = value.context.evidence.map((item) => parseEvidence(item, card.githubRepositoryId));
  if (value.context.canonicalProfile.githubRepositoryId !== card.githubRepositoryId
    || value.context.canonicalEvidence.githubRepositoryId !== card.githubRepositoryId
    || value.context.canonicalProfile.repository !== card.repository
    || value.context.canonicalEvidence.repository !== card.repository) {
    throw new Error('rardar_selection_detail_invalid');
  }
  return {
    ...value,
    context: { ...value.context, card, evidence },
  } as SelectionProjectDetail;
}

export async function loadSelectionProjectDetail(
  githubRepositoryId: number,
  selectionGeneration: string,
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<SelectionDetailLoadResult> {
  try {
    const response = await fetcher(
      `${backendUrl}/api/v1/rardar/discover/selection/projects/${githubRepositoryId}?selectionGeneration=${encodeURIComponent(selectionGeneration)}`,
      { cache: 'force-cache', headers: { Accept: 'application/json' } },
    );
    const payload: unknown = await response.json();
    if (response.ok) return { kind: 'published', detail: parseSelectionProjectDetail(payload) };
    if (response.status === 404) return { kind: 'not_found' };
    const detail = record(payload) && record(payload.detail) ? payload.detail : null;
    const code = detail && typeof detail.code === 'string' ? detail.code : 'rardar_selection_project_unavailable';
    return { kind: 'error', code };
  } catch {
    return { kind: 'error', code: 'rardar_selection_project_unavailable' };
  }
}
