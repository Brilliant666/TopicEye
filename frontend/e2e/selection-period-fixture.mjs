// Synthetic period API fixture. No real artifacts, repositories or Provider.
export const periodSelection = {
  mode: 'shadow', status: 'degraded', state: 'degraded', generation: 'fixture-current', currentGeneration: 'fixture-current',
  latestAttemptGeneration: 'fixture-failed-attempt', sourceObservation: 'fixture-observation', sourceTodayGeneration: 'fixture-today',
  generatedAt: '2026-09-03T02:00:00Z', latestCaptureAt: '2026-09-03T00:00:00Z', latestAttemptCaptureAt: '2026-09-10T00:00:00Z',
  items: [{ githubRepositoryId: 42, repository: 'fixture/period-project', htmlUrl: 'https://github.com/fixture/period-project',
    identitySummaryZh: '这是明确标记的合成浏览器测试项目。', corePositioningZh: null, whyWorthSeeingZh: '提供用于界面验收的合成资料，不代表真实模型判断。', whyNowZh: null,
    primaryReason: 'reference_or_learning_value', supportingReasons: [], category: 'dev-tools', categorySource: 'canonical_profile', productFormsZh: [],
    primaryLanguage: null, topics: [], licenseSpdxId: null, totalStars: 0, momentumLabel: null, reusableAssets: [], bestFit: [] }],
  categoryCounts: { 'dev-tools': 1 }, primaryReasonCounts: { reference_or_learning_value: 1 }, coverageLabelZh: '合成浏览器测试',
  candidateCount: 500, selectedCount: 1, publishedCount: 1, suppressedCount: 0, provenance: {}, code: null,
  recallCount: 500, executionMode: 'period', processedCount: 80, unprocessedCount: 420,
  profileReadyCount: 80, profileReboundCount: 0, profileRebuiltCount: 0, retryableFailureCount: 0, permanentFailureCount: 0,
  profileCoverage: 1, assessmentCoverage: 1, systemicFailure: false, safeFailureCodes: [], nextRetryAt: null,
};
