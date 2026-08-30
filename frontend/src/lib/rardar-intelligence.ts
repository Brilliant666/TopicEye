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
  defaultBranch?: string;
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
  defaultBranch?: string;
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

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
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

export type ProfileState = 'complete' | 'partial' | 'source_unavailable';
export type ProfileQualityState = 'ready' | 'partial' | 'rejected';
export type ProfileSourceLabel = '官方中文 README' | '官方 README（译）' | 'GitHub Description' | '官方原文' | '受限概括' | 'Rardar 整理';
export type TranslationState = 'not_needed' | 'translated' | 'pending' | 'unavailable';
export type OfficialNarrativeMode = 'official_zh' | 'official_translated' | 'rardar_derived' | 'insufficient';
export type PositioningSourceMode = OfficialNarrativeMode;
export type PositioningIncludedRole = 'identity' | 'core_mechanism' | 'primary_outcome';
export type PositioningExcludedRole = 'operation' | 'deployment' | 'validation' | 'example' | 'boundary';
export type OfficialNarrativeIssue =
  | 'tagline_missing'
  | 'positioning_missing'
  | 'highlights_missing'
  | 'highlight_title_missing'
  | 'highlight_order_unverified'
  | 'translation_pending'
  | 'source_structure_weak'
  | 'official_narrative_insufficient';

export interface ProjectCapability {
  title: string;
  detail: string;
  shortDetail: string | null;
  evidenceRefs: string[];
}

export interface OfficialHighlight {
  sourceOrder: number;
  sourceTitle: string;
  sourceDetail: string;
  titleZh: string;
  detailZh: string;
  evidenceRefs: string[];
}

export interface PositioningExcludedClause {
  role: PositioningExcludedRole;
  text: string;
  evidenceRefs: string[];
}

export interface TodayProject extends ExactExplosionProject {
  profileState: ProfileState;
  officialSummaryZh: string;
  sourceLabel: ProfileSourceLabel;
  sourceLanguage: string | null;
  capabilityBulletsZh: string[];
  capabilities: ProjectCapability[];
  translationState: TranslationState;
  identitySummaryZh: string;
  coreValueZh: string | null;
  coreValueEvidenceRefs: string[];
  keyDifferentiators: ProjectCapability[];
  productFormsZh: string[];
  qualityState: ProfileQualityState;
  qualityIssues: string[];
  officialTaglineZh: string | null;
  officialTaglineEvidenceRefs: string[];
  officialPositioningZh: string | null;
  officialPositioningEvidenceRefs: string[];
  positioningZh: string | null;
  positioningSourceMode: PositioningSourceMode;
  positioningEvidenceRefs: string[];
  positioningIncludedRoles: PositioningIncludedRole[];
  positioningExcludedClauses: PositioningExcludedClause[];
  officialHighlights: OfficialHighlight[];
  officialNarrativeMode: OfficialNarrativeMode;
  officialNarrativeIssues: OfficialNarrativeIssue[];
  rardarAssessmentZh: string | null;
  rardarAssessmentEvidenceRefs: string[];
  rardarDifferentiators: ProjectCapability[];
}

export interface ProfileSummary {
  total: number;
  complete: number;
  partial: number;
  sourceUnavailable: number;
  chineseSummaries: number;
  qualityReady?: number;
  qualityPartial?: number;
  qualityRejected?: number;
  officialZh?: number;
  officialTranslated?: number;
  rardarDerived?: number;
  insufficient?: number;
}

export interface TodaySnapshot extends Omit<ExplosionBoard, 'exactRanked' | 'state' | 'reason' | 'dataMode'> {
  schemaVersion: 1 | 2 | 3 | 4 | 5 | 6;
  state: 'ready' | 'warming_up' | 'baseline_missing' | 'not_ready';
  reason: 'explosion_artifact_not_published' | null;
  exactRanked: TodayProject[];
  dataMode: 'real' | 'demo';
  servingGenerationId: string;
  profileSummary: ProfileSummary;
}

export type TodayLoadResult =
  | { kind: 'published'; board: TodaySnapshot }
  | { kind: 'not_configured' }
  | { kind: 'error'; code: string };

export interface ReadmeSection {
  heading: string;
  path: string;
  purpose: 'overview' | 'capabilities' | 'use_cases' | 'quick_start' | 'architecture' | 'examples' | 'other';
  excerpts: string[];
  listItems: string[];
  evidenceRefs: string[];
}

export interface StartHereLink {
  label: string;
  path: string;
  htmlUrl: string;
  evidenceRefs: string[];
}

export interface ProjectDetail {
  schemaVersion: 1 | 2 | 3 | 4 | 5 | 6;
  generationId: string;
  servingGenerationId: string;
  project: TodayProject;
  profile: {
    profileSchemaVersion: 'rardar-project-profile-v1' | 'rardar-project-profile-v2' | 'rardar-project-profile-v3' | 'rardar-project-profile-v4' | 'rardar-project-profile-v5' | 'rardar-project-profile-v6';
    promptVersion: 'rardar-project-profile-zh-v1' | 'rardar-project-profile-zh-v2' | 'rardar-project-profile-zh-v3' | 'rardar-project-profile-zh-v4' | 'rardar-project-profile-zh-v5' | 'rardar-project-profile-zh-v6' | 'rardar-project-profile-zh-v7' | 'rardar-project-profile-zh-v8' | 'rardar-project-profile-zh-v9' | 'rardar-project-profile-zh-v10' | 'rardar-project-profile-zh-v11' | 'rardar-project-profile-zh-v12';
    githubRepositoryId: number;
    repository: string;
    htmlUrl: string;
    generationId: string;
    profileState: ProfileState;
    officialSummaryZh: string;
    sourceLabel: ProfileSourceLabel;
    sourceLanguage: string | null;
    capabilityBulletsZh: string[];
    capabilities: ProjectCapability[];
    productFormsZh: string[];
    supportedEnvironmentsZh: string[];
    primaryUseCasesZh: string[];
    deliveryFormsZh: string[];
    claimEvidenceRefs: Record<string, string[]>;
    readmePath: string | null;
    readmeBlobSha: string | null;
    selectedSections: ReadmeSection[];
    originalExcerpts: string[];
    startHere: StartHereLink[];
    evidenceDigest: string;
    generatedAt: string;
    translationState: TranslationState;
    identitySummaryZh: string;
    coreValueZh: string | null;
    coreValueEvidenceRefs: string[];
    keyDifferentiators: ProjectCapability[];
    qualityState: ProfileQualityState;
    qualityIssues: string[];
    officialTaglineZh: string | null;
    officialTaglineEvidenceRefs: string[];
    officialPositioningZh: string | null;
    officialPositioningEvidenceRefs: string[];
    positioningZh: string | null;
    positioningSourceMode: PositioningSourceMode;
    positioningEvidenceRefs: string[];
    positioningIncludedRoles: PositioningIncludedRole[];
    positioningExcludedClauses: PositioningExcludedClause[];
    officialHighlights: OfficialHighlight[];
    officialNarrativeMode: OfficialNarrativeMode;
    officialNarrativeIssues: OfficialNarrativeIssue[];
    officialNarrativePromptVersion: string | null;
    rardarAssessmentZh: string | null;
    rardarAssessmentEvidenceRefs: string[];
    rardarDifferentiators: ProjectCapability[];
    rardarAssessmentPromptVersion: string | null;
  };
  coverage: ExplosionCoverage | null;
  conflictCount: number;
  evidence: {
    schemaVersion: 1;
    githubRepositoryId: number;
    repository: string;
    generationId: string;
    readmePath: string | null;
    readmeBlobSha: string | null;
    sourceLanguage: string | null;
    selectedSections: ReadmeSection[];
    originalExcerpts: string[];
    topLevelTree: Array<{ path: string; type: string }>;
    evidenceIndex: Record<string, string>;
    pathRefs: Record<string, string>;
    digest: string;
  };
}

export type ProjectDetailLoadResult =
  | { kind: 'published'; detail: ProjectDetail }
  | { kind: 'not_found' }
  | { kind: 'revision_mismatch' }
  | { kind: 'error'; code: string };

type RardarRequestInit = RequestInit & { next?: { revalidate: number } };
type FetchLike = (input: string, init?: RardarRequestInit) => Promise<Response>;
const SERVING_REVALIDATE_SECONDS = 5;

export async function loadExplosionBoard(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<ExplosionBoardLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/explosion-board`, {
      cache: 'force-cache',
      next: { revalidate: SERVING_REVALIDATE_SECONDS },
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

export function parseTodaySnapshot(value: unknown): TodaySnapshot {
  const board = parseExplosionBoard(value);
  const schemaVersion = Number(isRecord(value) ? value.schemaVersion : NaN);
  if (!isRecord(value) || ![1, 2, 3, 4, 5, 6].includes(schemaVersion) || typeof value.servingGenerationId !== 'string') {
    throw new Error('rardar_response_invalid');
  }
  if (
    !isRecord(value.profileSummary)
    || !isFiniteInteger(value.profileSummary.total)
    || (schemaVersion >= 4 && (
      !isFiniteInteger(value.profileSummary.qualityReady)
      || !isFiniteInteger(value.profileSummary.qualityPartial)
      || !isFiniteInteger(value.profileSummary.qualityRejected)
    ))
    || (schemaVersion >= 5 && (
      !isFiniteInteger(value.profileSummary.officialZh)
      || !isFiniteInteger(value.profileSummary.officialTranslated)
      || !isFiniteInteger(value.profileSummary.rardarDerived)
      || !isFiniteInteger(value.profileSummary.insufficient)
    ))
  ) {
    throw new Error('rardar_response_invalid');
  }
  for (const item of value.exactRanked as unknown[]) {
    if (
      !isRecord(item)
      || !['complete', 'partial', 'source_unavailable'].includes(String(item.profileState))
      || typeof item.officialSummaryZh !== 'string'
      || item.officialSummaryZh.length === 0
      || !Array.isArray(item.capabilityBulletsZh)
      || (schemaVersion >= 3 && !Array.isArray(item.capabilities))
      || (Array.isArray(item.capabilities) && !item.capabilities.every(isProjectCapability))
      || (schemaVersion >= 4 && (
        !isStringArray(item.productFormsZh)
        || !isValidV4ProfileProjection(item)
      ))
      || (schemaVersion >= 5 && !isValidV5NarrativeProjection(item))
      || (schemaVersion >= 6 && !isValidV6PositioningProjection(item))
    ) {
      throw new Error('rardar_response_invalid');
    }
  }
  if (schemaVersion >= 4) {
    const profiles = value.exactRanked as Array<Record<string, unknown>>;
    const qualityReady = profiles.filter((item) => item.qualityState === 'ready').length;
    const qualityPartial = profiles.filter((item) => item.qualityState === 'partial').length;
    const qualityRejected = profiles.filter((item) => item.qualityState === 'rejected').length;
    if (
      value.profileSummary.qualityReady !== qualityReady
      || value.profileSummary.qualityPartial !== qualityPartial
      || value.profileSummary.qualityRejected !== qualityRejected
    ) {
      throw new Error('rardar_response_invalid');
    }
  }
  if (schemaVersion >= 5) {
    const profiles = value.exactRanked as Array<Record<string, unknown>>;
    const modeCounts = {
      official_zh: profiles.filter((item) => item.officialNarrativeMode === 'official_zh').length,
      official_translated: profiles.filter((item) => item.officialNarrativeMode === 'official_translated').length,
      rardar_derived: profiles.filter((item) => item.officialNarrativeMode === 'rardar_derived').length,
      insufficient: profiles.filter((item) => item.officialNarrativeMode === 'insufficient').length,
    };
    if (
      value.profileSummary.officialZh !== modeCounts.official_zh
      || value.profileSummary.officialTranslated !== modeCounts.official_translated
      || value.profileSummary.rardarDerived !== modeCounts.rardar_derived
      || value.profileSummary.insufficient !== modeCounts.insufficient
    ) {
      throw new Error('rardar_response_invalid');
    }
  }
  const exactRanked = (value.exactRanked as Array<Record<string, unknown>>).map((item) => ({
    ...item,
    capabilities: Array.isArray(item.capabilities) ? item.capabilities : [],
    identitySummaryZh: typeof item.identitySummaryZh === 'string' ? item.identitySummaryZh : item.officialSummaryZh,
    coreValueZh: typeof item.coreValueZh === 'string' ? item.coreValueZh : null,
    coreValueEvidenceRefs: Array.isArray(item.coreValueEvidenceRefs) ? item.coreValueEvidenceRefs : [],
    keyDifferentiators: Array.isArray(item.keyDifferentiators) ? item.keyDifferentiators : [],
    productFormsZh: Array.isArray(item.productFormsZh) ? item.productFormsZh : [],
    qualityState: ['ready', 'partial', 'rejected'].includes(String(item.qualityState))
      ? item.qualityState
      : 'partial',
    qualityIssues: Array.isArray(item.qualityIssues) ? item.qualityIssues : [],
    ...normalizeNarrativeProjection(item, schemaVersion),
  }));
  return { ...board, ...value, exactRanked } as unknown as TodaySnapshot;
}

function isProjectCapability(value: unknown): value is ProjectCapability {
  return isRecord(value)
    && typeof value.title === 'string'
    && value.title.length > 0
    && typeof value.detail === 'string'
    && value.detail.length > 0
    && (value.shortDetail === null || typeof value.shortDetail === 'string')
    && Array.isArray(value.evidenceRefs)
    && value.evidenceRefs.every((reference) => typeof reference === 'string');
}

function isOfficialHighlight(value: unknown): value is OfficialHighlight {
  return isRecord(value)
    && isFiniteInteger(value.sourceOrder)
    && value.sourceOrder >= 1
    && value.sourceOrder <= 8
    && typeof value.sourceTitle === 'string'
    && value.sourceTitle.length > 0
    && typeof value.sourceDetail === 'string'
    && value.sourceDetail.length > 0
    && typeof value.titleZh === 'string'
    && value.titleZh.length > 0
    && typeof value.detailZh === 'string'
    && value.detailZh.length > 0
    && isStringArray(value.evidenceRefs)
    && value.evidenceRefs.length > 0;
}

const narrativeModes: OfficialNarrativeMode[] = [
  'official_zh',
  'official_translated',
  'rardar_derived',
  'insufficient',
];

const narrativeIssues: OfficialNarrativeIssue[] = [
  'tagline_missing',
  'positioning_missing',
  'highlights_missing',
  'highlight_title_missing',
  'highlight_order_unverified',
  'translation_pending',
  'source_structure_weak',
  'official_narrative_insufficient',
];

const narrativeSourceLabels: Record<OfficialNarrativeMode, ProfileSourceLabel> = {
  official_zh: '官方中文 README',
  official_translated: '官方 README（译）',
  rardar_derived: 'Rardar 整理',
  insufficient: '受限概括',
};

export function narrativeSourceLabel(mode: OfficialNarrativeMode): ProfileSourceLabel {
  return narrativeSourceLabels[mode];
}

export function positioningSourceLabel(mode: PositioningSourceMode): ProfileSourceLabel {
  return narrativeSourceLabels[mode];
}

const positioningIncludedRoles: PositioningIncludedRole[] = ['identity', 'core_mechanism', 'primary_outcome'];
const positioningExcludedRoles: PositioningExcludedRole[] = [
  'operation',
  'deployment',
  'validation',
  'example',
  'boundary',
];

function isPositioningExcludedClause(value: unknown): value is PositioningExcludedClause {
  return isRecord(value)
    && positioningExcludedRoles.includes(value.role as PositioningExcludedRole)
    && typeof value.text === 'string'
    && value.text.length > 0
    && isStringArray(value.evidenceRefs)
    && value.evidenceRefs.length > 0;
}

function isValidV6PositioningProjection(value: Record<string, unknown>): boolean {
  if (
    !narrativeModes.includes(value.positioningSourceMode as PositioningSourceMode)
    || !(value.positioningZh === null || typeof value.positioningZh === 'string')
    || !isStringArray(value.positioningEvidenceRefs)
    || !isStringArray(value.positioningIncludedRoles)
    || !value.positioningIncludedRoles.every((role) => positioningIncludedRoles.includes(role as PositioningIncludedRole))
    || new Set(value.positioningIncludedRoles).size !== value.positioningIncludedRoles.length
    || !Array.isArray(value.positioningExcludedClauses)
    || !value.positioningExcludedClauses.every(isPositioningExcludedClause)
    || value.officialPositioningZh !== value.positioningZh
    || JSON.stringify(value.officialPositioningEvidenceRefs) !== JSON.stringify(value.positioningEvidenceRefs)
  ) return false;
  if (value.positioningSourceMode === 'insufficient') {
    return value.positioningZh === null
      && value.positioningEvidenceRefs.length === 0
      && value.positioningIncludedRoles.length === 0
      && value.positioningExcludedClauses.length === 0;
  }
  return typeof value.positioningZh === 'string'
    && value.positioningEvidenceRefs.length > 0
    && value.positioningIncludedRoles.length > 0;
}

function isValidV5NarrativeProjection(value: Record<string, unknown>): boolean {
  if (
    !narrativeModes.includes(value.officialNarrativeMode as OfficialNarrativeMode)
    || !isStringArray(value.officialNarrativeIssues)
    || !value.officialNarrativeIssues.every((issue) => narrativeIssues.includes(issue as OfficialNarrativeIssue))
    || new Set(value.officialNarrativeIssues).size !== value.officialNarrativeIssues.length
    || !(value.officialTaglineZh === null || typeof value.officialTaglineZh === 'string')
    || !isStringArray(value.officialTaglineEvidenceRefs)
    || !(value.officialPositioningZh === null || typeof value.officialPositioningZh === 'string')
    || !isStringArray(value.officialPositioningEvidenceRefs)
    || !Array.isArray(value.officialHighlights)
    || !value.officialHighlights.every(isOfficialHighlight)
    || !(value.rardarAssessmentZh === null || typeof value.rardarAssessmentZh === 'string')
    || !isStringArray(value.rardarAssessmentEvidenceRefs)
    || !Array.isArray(value.rardarDifferentiators)
    || !value.rardarDifferentiators.every(isProjectCapability)
  ) return false;

  const mode = value.officialNarrativeMode as OfficialNarrativeMode;
  const highlights = value.officialHighlights as OfficialHighlight[];
  if (value.sourceLabel !== narrativeSourceLabels[mode]) return false;
  if (highlights.some((highlight, index) => highlight.sourceOrder !== index + 1)) return false;
  if (mode === 'official_zh' && highlights.some(
    (highlight) => highlight.sourceTitle !== highlight.titleZh || highlight.sourceDetail !== highlight.detailZh,
  )) return false;
  if (mode === 'official_zh' || mode === 'official_translated') {
    if (
      typeof value.officialTaglineZh !== 'string'
      || value.officialTaglineEvidenceRefs.length === 0
      || typeof value.officialPositioningZh !== 'string'
      || value.officialPositioningEvidenceRefs.length === 0
      || highlights.length === 0
    ) return false;
  }
  if (mode === 'insufficient' && (
    value.officialTaglineZh !== null
    || value.officialPositioningZh !== null
    || highlights.length > 0
    || value.rardarAssessmentZh !== null
    || value.rardarDifferentiators.length > 0
  )) return false;
  if (value.officialTaglineZh !== null && value.identitySummaryZh !== value.officialTaglineZh) return false;
  if (value.coreValueZh !== value.rardarAssessmentZh) return false;
  if (JSON.stringify(value.coreValueEvidenceRefs) !== JSON.stringify(value.rardarAssessmentEvidenceRefs)) return false;
  if (JSON.stringify(value.keyDifferentiators) !== JSON.stringify(value.rardarDifferentiators)) return false;
  return true;
}

function normalizeNarrativeProjection(
  value: Record<string, unknown>,
  schemaVersion: number,
): Pick<TodayProject,
  | 'officialTaglineZh'
  | 'officialTaglineEvidenceRefs'
  | 'officialPositioningZh'
  | 'officialPositioningEvidenceRefs'
  | 'positioningZh'
  | 'positioningSourceMode'
  | 'positioningEvidenceRefs'
  | 'positioningIncludedRoles'
  | 'positioningExcludedClauses'
  | 'officialHighlights'
  | 'officialNarrativeMode'
  | 'officialNarrativeIssues'
  | 'rardarAssessmentZh'
  | 'rardarAssessmentEvidenceRefs'
  | 'rardarDifferentiators'> {
  if (schemaVersion >= 5) {
    const mode = value.officialNarrativeMode as OfficialNarrativeMode;
    return {
      officialTaglineZh: value.officialTaglineZh as string | null,
      officialTaglineEvidenceRefs: value.officialTaglineEvidenceRefs as string[],
      officialPositioningZh: value.officialPositioningZh as string | null,
      officialPositioningEvidenceRefs: value.officialPositioningEvidenceRefs as string[],
      positioningZh: schemaVersion >= 6
        ? value.positioningZh as string | null
        : value.officialPositioningZh as string | null,
      positioningSourceMode: schemaVersion >= 6
        ? value.positioningSourceMode as PositioningSourceMode
        : (value.officialPositioningZh === null ? 'insufficient' : mode),
      positioningEvidenceRefs: schemaVersion >= 6
        ? value.positioningEvidenceRefs as string[]
        : value.officialPositioningEvidenceRefs as string[],
      positioningIncludedRoles: schemaVersion >= 6
        ? value.positioningIncludedRoles as PositioningIncludedRole[]
        : [],
      positioningExcludedClauses: schemaVersion >= 6
        ? value.positioningExcludedClauses as PositioningExcludedClause[]
        : [],
      officialHighlights: value.officialHighlights as OfficialHighlight[],
      officialNarrativeMode: mode,
      officialNarrativeIssues: value.officialNarrativeIssues as OfficialNarrativeIssue[],
      rardarAssessmentZh: value.rardarAssessmentZh as string | null,
      rardarAssessmentEvidenceRefs: value.rardarAssessmentEvidenceRefs as string[],
      rardarDifferentiators: value.rardarDifferentiators as ProjectCapability[],
    };
  }
  const qualityState = String(value.qualityState);
  const insufficient = qualityState === 'rejected';
  const tagline = insufficient
    ? null
    : (typeof value.identitySummaryZh === 'string' ? value.identitySummaryZh : String(value.officialSummaryZh));
  return {
    officialTaglineZh: tagline,
    officialTaglineEvidenceRefs: [],
    officialPositioningZh: null,
    officialPositioningEvidenceRefs: [],
    positioningZh: null,
    positioningSourceMode: 'insufficient',
    positioningEvidenceRefs: [],
    positioningIncludedRoles: [],
    positioningExcludedClauses: [],
    officialHighlights: [],
    officialNarrativeMode: insufficient ? 'insufficient' : 'rardar_derived',
    officialNarrativeIssues: insufficient
      ? ['positioning_missing', 'highlights_missing', 'source_structure_weak', 'official_narrative_insufficient']
      : ['positioning_missing', 'highlights_missing', 'source_structure_weak'],
    rardarAssessmentZh: typeof value.coreValueZh === 'string' ? value.coreValueZh : null,
    rardarAssessmentEvidenceRefs: Array.isArray(value.coreValueEvidenceRefs)
      ? value.coreValueEvidenceRefs as string[]
      : [],
    rardarDifferentiators: Array.isArray(value.keyDifferentiators)
      ? value.keyDifferentiators as ProjectCapability[]
      : [],
  };
}

function isValidV4ProfileProjection(value: Record<string, unknown>): boolean {
  if (
    typeof value.identitySummaryZh !== 'string'
    || value.identitySummaryZh.length === 0
    || value.identitySummaryZh !== value.officialSummaryZh
    || !(value.coreValueZh === null || typeof value.coreValueZh === 'string')
    || !['ready', 'partial', 'rejected'].includes(String(value.qualityState))
    || !isStringArray(value.qualityIssues)
    || new Set(value.qualityIssues).size !== value.qualityIssues.length
    || value.qualityIssues.some((issue) => issue.length === 0 || issue.length > 80)
    || !isStringArray(value.coreValueEvidenceRefs)
    || !Array.isArray(value.keyDifferentiators)
    || !value.keyDifferentiators.every(isProjectCapability)
  ) {
    return false;
  }
  if (value.coreValueZh !== null && value.coreValueEvidenceRefs.length === 0) return false;
  if (value.qualityState === 'ready') {
    return typeof value.coreValueZh === 'string'
      && value.coreValueEvidenceRefs.length > 0
      && value.keyDifferentiators.length > 0
      && Array.isArray(value.capabilities)
      && value.capabilities.length > 0
      && value.qualityIssues.length === 0;
  }
  if (value.qualityState === 'rejected') {
    return value.coreValueZh === null
      && value.keyDifferentiators.length === 0
      && Array.isArray(value.capabilities)
      && value.capabilities.length === 0
      && value.qualityIssues.length > 0;
  }
  return true;
}

export async function loadTodaySnapshot(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<TodayLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/today`, {
      cache: 'force-cache',
      next: { revalidate: SERVING_REVALIDATE_SECONDS },
      headers: { Accept: 'application/json' },
    });
    const payload: unknown = await response.json();
    if (response.ok) return { kind: 'published', board: parseTodaySnapshot(payload) };
    const detail = isRecord(payload) && isRecord(payload.detail) ? payload.detail : null;
    const code = detail && typeof detail.code === 'string' ? detail.code : 'rardar_intelligence_unavailable';
    if (response.status === 503 && code === 'rardar_serving_unavailable') return { kind: 'not_configured' };
    return { kind: 'error', code };
  } catch {
    return { kind: 'error', code: 'rardar_intelligence_unavailable' };
  }
}

export function parseProjectDetail(value: unknown): ProjectDetail {
  const schemaVersion = Number(isRecord(value) ? value.schemaVersion : NaN);
  if (!isRecord(value) || ![1, 2, 3, 4, 5, 6].includes(schemaVersion) || !isRecord(value.project) || !isRecord(value.profile) || !isRecord(value.evidence)) {
    throw new Error('rardar_project_response_invalid');
  }
  const identifier = value.project.githubRepositoryId;
  if (
    !isFiniteInteger(identifier)
    || identifier <= 0
    || value.profile.githubRepositoryId !== identifier
    || value.evidence.githubRepositoryId !== identifier
    || typeof value.generationId !== 'string'
    || value.profile.generationId !== value.generationId
    || value.evidence.generationId !== value.generationId
    || typeof value.project.officialSummaryZh !== 'string'
    || (schemaVersion >= 3 && !Array.isArray(value.project.capabilities))
    || (Array.isArray(value.project.capabilities) && !value.project.capabilities.every(isProjectCapability))
    || typeof value.profile.officialSummaryZh !== 'string'
    || !Array.isArray(value.profile.capabilityBulletsZh)
    || (schemaVersion >= 3 && !Array.isArray(value.profile.capabilities))
    || (Array.isArray(value.profile.capabilities) && !value.profile.capabilities.every(isProjectCapability))
    || !Array.isArray(value.profile.selectedSections)
    || !Array.isArray(value.profile.startHere)
    || (schemaVersion >= 4 && (
      !isStringArray(value.project.productFormsZh)
      || !isValidV4ProfileProjection(value.project)
    ))
    || (schemaVersion >= 4 && !isValidV4ProfileProjection(value.profile))
    || (schemaVersion >= 5 && !isValidV5NarrativeProjection(value.project))
    || (schemaVersion >= 5 && !isValidV5NarrativeProjection(value.profile))
    || (schemaVersion >= 6 && !isValidV6PositioningProjection(value.project))
    || (schemaVersion >= 6 && !isValidV6PositioningProjection(value.profile))
    || (schemaVersion >= 5 && (
      typeof value.profile.officialNarrativePromptVersion !== 'string'
      || typeof value.profile.rardarAssessmentPromptVersion !== 'string'
    ))
  ) {
    throw new Error('rardar_project_response_invalid');
  }
  if (schemaVersion >= 4 && (
    value.project.officialSummaryZh !== value.profile.officialSummaryZh
    || value.project.identitySummaryZh !== value.profile.identitySummaryZh
    || value.project.coreValueZh !== value.profile.coreValueZh
    || JSON.stringify(value.project.coreValueEvidenceRefs) !== JSON.stringify(value.profile.coreValueEvidenceRefs)
    || JSON.stringify(value.project.keyDifferentiators) !== JSON.stringify(value.profile.keyDifferentiators)
    || JSON.stringify(value.project.capabilities) !== JSON.stringify((value.profile.capabilities as unknown[]).slice(0, 4))
    || JSON.stringify(value.project.productFormsZh) !== JSON.stringify((value.profile.productFormsZh as unknown[]).slice(0, 3))
    || value.project.qualityState !== value.profile.qualityState
    || JSON.stringify(value.project.qualityIssues) !== JSON.stringify(value.profile.qualityIssues)
    || (schemaVersion >= 5 && (
      value.project.officialTaglineZh !== value.profile.officialTaglineZh
      || JSON.stringify(value.project.officialTaglineEvidenceRefs) !== JSON.stringify(value.profile.officialTaglineEvidenceRefs)
      || value.project.officialPositioningZh !== value.profile.officialPositioningZh
      || JSON.stringify(value.project.officialPositioningEvidenceRefs) !== JSON.stringify(value.profile.officialPositioningEvidenceRefs)
      || JSON.stringify(value.project.officialHighlights) !== JSON.stringify(value.profile.officialHighlights)
      || value.project.officialNarrativeMode !== value.profile.officialNarrativeMode
      || JSON.stringify(value.project.officialNarrativeIssues) !== JSON.stringify(value.profile.officialNarrativeIssues)
      || value.project.rardarAssessmentZh !== value.profile.rardarAssessmentZh
      || JSON.stringify(value.project.rardarAssessmentEvidenceRefs) !== JSON.stringify(value.profile.rardarAssessmentEvidenceRefs)
      || JSON.stringify(value.project.rardarDifferentiators) !== JSON.stringify(value.profile.rardarDifferentiators)
      || (schemaVersion >= 6 && (
        value.project.positioningZh !== value.profile.positioningZh
        || value.project.positioningSourceMode !== value.profile.positioningSourceMode
        || JSON.stringify(value.project.positioningEvidenceRefs) !== JSON.stringify(value.profile.positioningEvidenceRefs)
        || JSON.stringify(value.project.positioningIncludedRoles) !== JSON.stringify(value.profile.positioningIncludedRoles)
        || JSON.stringify(value.project.positioningExcludedClauses) !== JSON.stringify(value.profile.positioningExcludedClauses)
      ))
    ))
  )) {
    throw new Error('rardar_project_response_invalid');
  }
  const normalizedProfile = {
    ...value.profile,
    productFormsZh: Array.isArray(value.profile.productFormsZh) ? value.profile.productFormsZh : [],
    supportedEnvironmentsZh: Array.isArray(value.profile.supportedEnvironmentsZh)
      ? value.profile.supportedEnvironmentsZh
      : [],
    capabilities: Array.isArray(value.profile.capabilities) ? value.profile.capabilities : [],
    identitySummaryZh: typeof value.profile.identitySummaryZh === 'string'
      ? value.profile.identitySummaryZh
      : value.profile.officialSummaryZh,
    coreValueZh: typeof value.profile.coreValueZh === 'string' ? value.profile.coreValueZh : null,
    coreValueEvidenceRefs: Array.isArray(value.profile.coreValueEvidenceRefs)
      ? value.profile.coreValueEvidenceRefs
      : [],
    keyDifferentiators: Array.isArray(value.profile.keyDifferentiators)
      ? value.profile.keyDifferentiators
      : [],
    qualityState: ['ready', 'partial', 'rejected'].includes(String(value.profile.qualityState))
      ? value.profile.qualityState
      : 'partial',
    qualityIssues: Array.isArray(value.profile.qualityIssues) ? value.profile.qualityIssues : [],
    ...normalizeNarrativeProjection(value.profile, schemaVersion),
    officialNarrativePromptVersion: typeof value.profile.officialNarrativePromptVersion === 'string'
      ? value.profile.officialNarrativePromptVersion
      : null,
    rardarAssessmentPromptVersion: typeof value.profile.rardarAssessmentPromptVersion === 'string'
      ? value.profile.rardarAssessmentPromptVersion
      : null,
  };
  const normalizedProject = {
    ...value.project,
    capabilities: Array.isArray(value.project.capabilities) ? value.project.capabilities : [],
    identitySummaryZh: typeof value.project.identitySummaryZh === 'string'
      ? value.project.identitySummaryZh
      : value.project.officialSummaryZh,
    coreValueZh: typeof value.project.coreValueZh === 'string' ? value.project.coreValueZh : null,
    coreValueEvidenceRefs: Array.isArray(value.project.coreValueEvidenceRefs)
      ? value.project.coreValueEvidenceRefs
      : [],
    keyDifferentiators: Array.isArray(value.project.keyDifferentiators)
      ? value.project.keyDifferentiators
      : [],
    productFormsZh: Array.isArray(value.project.productFormsZh) ? value.project.productFormsZh : [],
    qualityState: ['ready', 'partial', 'rejected'].includes(String(value.project.qualityState))
      ? value.project.qualityState
      : 'partial',
    qualityIssues: Array.isArray(value.project.qualityIssues) ? value.project.qualityIssues : [],
    ...normalizeNarrativeProjection(value.project, schemaVersion),
  };
  return {
    ...value,
    project: normalizedProject,
    profile: normalizedProfile,
    coverage: isRecord(value.coverage) ? value.coverage : null,
    conflictCount: isFiniteInteger(value.conflictCount) ? value.conflictCount : 0,
  } as unknown as ProjectDetail;
}

export async function loadProjectDetail(
  githubRepositoryId: number,
  generationId: string,
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<ProjectDetailLoadResult> {
  try {
    const response = await fetcher(
      `${backendUrl}/api/v1/rardar/projects/${githubRepositoryId}?generationId=${encodeURIComponent(generationId)}`,
      {
        cache: 'force-cache',
        next: { revalidate: SERVING_REVALIDATE_SECONDS },
        headers: { Accept: 'application/json' },
      },
    );
    const payload: unknown = await response.json();
    if (response.ok) return { kind: 'published', detail: parseProjectDetail(payload) };
    const detail = isRecord(payload) && isRecord(payload.detail) ? payload.detail : null;
    const code = detail && typeof detail.code === 'string' ? detail.code : 'rardar_project_unavailable';
    if (response.status === 404) return { kind: 'not_found' };
    if (response.status === 409) return { kind: 'revision_mismatch' };
    return { kind: 'error', code };
  } catch {
    return { kind: 'error', code: 'rardar_project_unavailable' };
  }
}
