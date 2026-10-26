// Synthetic persisted reading and identity only. Not real project evidence,
// production credentials, backend authorization coverage, or a Provider probe.
export const syntheticReader = {
  id: 2,
  email: 'synthetic-reader@example.test',
  display_name: 'Synthetic browser reader',
  role: 'user',
  plan: 'free',
  is_active: true,
  created_at: '2026-09-10T00:00:00Z',
};

export function savedSharedInsight(project, generationId) {
  return {
    state: 'ready', errorCode: null,
    result: {
      state: 'ready', repository: project.repository, githubRepositoryId: null,
      generationId, promptVersion: 'rardar-project-insight-v5',
      schemaVersion: 'rardar-project-insight-schema-v5', format: 'structured',
      officialIntro: { text: 'Synthetic saved introduction.', evidenceRefs: ['readme:fixture'], sourceLabel: 'AI受限概括' },
      analysis: {
        conclusionSummary: { text: '合成已保存解读：匿名阅读不会重新生成。', evidenceRefs: ['readme:fixture'] },
        differentiators: [], reusableAssets: [],
        reuseCost: { level: 'unknown', reason: '仅测试保存结果的公开阅读。', evidenceRefs: ['readme:fixture'] },
        bestFitScenarios: [], startHere: [], implementationBoundaries: [],
      },
      errorCode: null, model: 'synthetic-saved-fixture', provider: 'no-provider',
      cacheHit: true, evidenceDigest: 'e'.repeat(64), evidenceCacheHit: true,
      evidenceKinds: ['readme'],
    },
  };
}
