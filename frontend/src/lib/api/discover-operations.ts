import { request } from './_core';

export type DiscoverPlan = {
  id: string;
  candidates: Array<{ githubRepositoryId: number; repository: string }>;
  candidateCount: number;
  sourceObservationSetId: string;
  todayGenerationId: string;
  latestCaptureAt: string | null;
  requestLimit: number;
  recallBatchId: string;
};
export type DiscoverOperation = {
  id: string;
  status: 'running' | 'completed' | 'empty' | 'failed' | 'interrupted' | 'not_configured';
  plan: DiscoverPlan;
  providerCalls: number;
  startedAt: string;
  completedAt: string | null;
  errorCode?: string | null;
  result: {
    processedCount: number;
    publishedCount: number;
    failedCount: number;
    cacheHits: number;
    generationId: string | null;
    installed: boolean;
    stopped?: boolean;
    stopReason?: string | null;
    failures: Array<{ repository: string; reason: string }>;
  } | null;
};
const endpoint = '/rardar/discover/operations';
export const discoverOperationsApi = {
  current: () => request<{ latest: DiscoverOperation | null; prepared?: DiscoverPlan | null; requestLimit: number; batchSize: number }>(endpoint, { cache: 'no-store' }),
  prepare: (requestId: string) => request<DiscoverPlan>(`${endpoint}/prepare`, { method: 'POST', body: JSON.stringify({ requestId }) }),
  start: (requestId: string, planId: string) => request<DiscoverOperation>(endpoint, { method: 'POST', body: JSON.stringify({ requestId, planId }) }),
};
export function discoverOperationLabel(status: DiscoverOperation['status']) {
  return { running: '正在生成本批精选', completed: '本批处理完成', empty: '本批没有入选项目', failed: '本批未能完成', interrupted: '本批执行已中断', not_configured: '评估尚未配置' }[status];
}
