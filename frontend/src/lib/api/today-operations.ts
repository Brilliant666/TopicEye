import { request } from './_core';

export type TodayOperation = {
  id: string;
  scope?: 'dual_board' | 'exact_explosion';
  status: 'running' | 'updated' | 'partial' | 'unchanged' | 'no_complete_board' | 'failed' | 'interrupted' | 'not_configured';
  startedAt: string;
  completedAt: string | null;
  errorCode: string | null;
  providerCalls: 0;
  result: {
    generationId: string | null;
    window: { startedAt: string; endedAt: string } | null;
    syncedAt: string | null;
    changed: boolean;
    sources?: Array<{ source: string; status: string; sourceDate?: string | null; errorCode?: string | null }>;
  } | null;
};

const endpoint = '/rardar/today/operations';
export const todayOperationsApi = {
  current: () => request<{ latest: TodayOperation | null; lastSuccessfulSyncAt?: string | null }>(endpoint, { cache: 'no-store' }),
  get: (id: string) => request<TodayOperation>(`${endpoint}/${encodeURIComponent(id)}`, { cache: 'no-store' }),
  // A caller cannot supply upstream hosts, paths, commands or generation options.
  start: (requestId: string) => request<TodayOperation>(endpoint, { method: 'POST', body: JSON.stringify({ requestId }) }),
};

export function todayOperationLabel(status: TodayOperation['status']): string {
  return {
    running: '正在检查 / 同步', updated: '已更新', partial: '部分来源已更新', unchanged: '已是最新',
    no_complete_board: '暂时没有更新的完整榜单', failed: '连接或验证失败',
    interrupted: '同步已中断', not_configured: '只读同步尚未配置',
  }[status];
}
