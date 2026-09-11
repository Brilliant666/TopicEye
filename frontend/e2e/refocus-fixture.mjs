// Explicit synthetic browser fixtures; never presented as live source evidence.
const generationId = 'boards-' + 'a'.repeat(64);
const fullProfile = {
  repository: 'fixture/project-0', htmlUrl: 'https://github.com/fixture/project-0',
  officialTaglineZh: '用于示例技术文档的合成档案', identitySummaryZh: '用于示例技术文档的合成档案',
  positioningZh: '从已保存材料理解项目边界', positioningSourceMode: 'rardar_derived', positioningEvidenceRefs: ['readme:fixture'], positioningExcludedClauses: [],
  coreValueZh: null, coreValueEvidenceRefs: [],
  productFormsZh: ['文档工具'], supportedEnvironmentsZh: ['本地部署'], deliveryFormsZh: ['静态页面'], primaryUseCasesZh: ['团队资料阅读'],
  capabilities: Array.from({ length: 4 }, (_, index) => ({ title: `合成能力 ${index + 1}`, detail: `合成说明 ${index + 1}，仅验证完整资料展示。`, evidenceRefs: ['readme:fixture'], sourceMode: 'rardar_derived' })),
  rardarAssessmentZh: '合成判断仅用于浏览器接线', rardarAssessmentEvidenceRefs: ['readme:fixture'],
  rardarDifferentiators: Array.from({ length: 2 }, (_, index) => ({ title: `合成差异 ${index + 1}`, detail: '说明只验证展示，不代表真实项目分析。', evidenceRefs: ['readme:fixture'] })),
  keyDifferentiators: [], officialHighlights: [], officialNarrativeMode: 'rardar_derived', qualityState: 'ready', materialState: 'complete',
  startHere: Array.from({ length: 9 }, (_, index) => ({ label: `资料入口 ${index + 1}`, path: `docs/fixture-${index + 1}.md`, htmlUrl: `https://github.com/fixture/project-0/blob/main/docs/fixture-${index + 1}.md`, evidenceRefs: ['readme:fixture'] })),
  generatedAt: '2026-09-09T00:00:00Z', selectedSections: [], originalExcerpts: ['Synthetic evidence excerpt, not real project output.'],
  sourceLabel: 'Rardar 整理', readmePath: 'README.md', readmeBlobSha: 'c'.repeat(40), evidenceDigest: 'd'.repeat(64), translationState: 'translated',
};
export const refocusBoard = {
  schemaVersion: 1, generationId, publishedAt: '2026-09-10T00:00:00Z', checkedAt: '2026-09-10T00:00:00Z',
  sources: ['github', 'trendshift'].map(source => ({ source, label: source === 'github' ? 'GitHub Trending' : 'Trendshift', status: 'healthy', sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', count: 12, errorCode: null })),
  projects: Array.from({ length: 23 }, (_, i) => ({
    projectId: `fixture-project-${i}--` + 'b'.repeat(20), repository: `fixture/project-${i}`, repositoryUrl: `https://github.com/fixture/project-${i}`, githubRepositoryId: null,
    description: i === 0 ? 'A real-material shape, synthetic fixture content.' : null, totalStars: null, dualListed: i === 0,
    appearances: (i === 0 ? ['github', 'trendshift'] : [i % 2 ? 'github' : 'trendshift']).map(source => ({ source, rank: i + 1, sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null })),
    materialState: i === 0 ? 'complete' : 'unavailable', profile: null, displayProfile: i === 0 ? fullProfile : null, historyAppearances: 1, firstSeenAt: null, lastSeenAt: null,
  })),
};
