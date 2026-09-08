import { request } from './_core';

export type NewsOperation = {
  id: string;
  action: 'refresh' | 'enhance';
  status: 'running' | 'completed' | 'degraded' | 'failed' | 'interrupted' | 'budget_exhausted' | 'paused';
  startedAt: string;
  completedAt: string | null;
  errorCode: string | null;
  itemIds: number[];
  requestLimit: number;
  result: {
    providerCalls: number;
    considered?: number;
    enhanced?: number;
    cacheHits?: number;
    alreadyChinese?: number;
    failed?: number;
    budgetRemaining?: number;
    sources?: { key: string; status: string; created: number; duplicates: number; retained: number }[];
    items?: { contentId: number; status: string; materialKind: string | null; errorCode: string | null }[];
  } | null;
};

export type NewsOperationInput = {
  action: 'refresh' | 'enhance'; requestId: string;
  source?: string; topic?: string; sort: 'balanced' | 'latest'; page: number;
};

const endpoint = '/rardar/hotspot-news/operations';
export const newsOperationsApi = {
  current: () => request<{ requestLimit: number; pageSize: number; latest: NewsOperation | null }>(endpoint, { cache: 'no-store' }),
  get: (id: string) => request<NewsOperation>(`${endpoint}/${encodeURIComponent(id)}`, { cache: 'no-store' }),
  start: (input: NewsOperationInput) => request<NewsOperation>(endpoint, { method: 'POST', body: JSON.stringify(input) }),
};

export function newsOperationLabel(status: NewsOperation['status']): string {
  return { running: '正在执行', completed: '已完成', degraded: '部分完成', failed: '执行失败', interrupted: '执行已中断', budget_exhausted: '额度已用尽', paused: '来源已暂停，未执行采集' }[status];
}
