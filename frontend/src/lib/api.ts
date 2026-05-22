/**
 * TopicEye API Client
 * Backend API wrapper using fetch
 */

import type {
  Source,
  CreateSourceRequest,
  UpdateSourceRequest,
  ContentItem,
  ContentAnalysis,
  TopicFilterParams,
  ContentFilterParams,
  PaginatedResponse,
  SyncResult,
  TopicInfo,
  WeeklyDigest,
  WeeklyDigestListResponse,
  WeeklyDigestWeeksResponse,
} from '@/types';

export type { CreateSourceRequest, UpdateSourceRequest };

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

/** Generic fetch wrapper with error handling */
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.message || `API Error: ${response.status}`);
  }

  return response.json();
}

// ─── Sources API ───

export const sourcesApi = {
  /** 获取信源列表 */
  list(): Promise<PaginatedResponse<Source> & { total?: number }> {
    return request('/sources');
  },

  /** 获取单个信源 */
  get(id: number): Promise<Source> {
    return request(`/sources/${id}`);
  },

  /** 添加信源 */
  create(data: CreateSourceRequest): Promise<Source> {
    return request('/sources', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** 更新信源 */
  update(id: number, data: UpdateSourceRequest): Promise<Source> {
    return request(`/sources/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** 删除信源 */
  delete(id: number): Promise<void> {
    return request(`/sources/${id}`, { method: 'DELETE' });
  },

  /** 手动触发同步 */
  sync(id: number): Promise<SyncResult> {
    return request(`/sources/${id}/sync`, { method: 'POST' });
  },

  /** 从 OPML 文件导入 RSS 源（Folo/Follow 导出） */
  importOPML(file: File): Promise<{ created: number; skipped: number; total: number; message: string }> {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${BASE_URL}/sources/import-opml`, {
      method: 'POST',
      body: formData,
    }).then(r => r.json());
  },
};

// ─── Contents API ───

export const contentsApi = {
  /** 获取内容列表 */
  list(params?: ContentFilterParams): Promise<PaginatedResponse<ContentItem>> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/contents${query}`);
  },

  /** 获取单条内容 */
  get(id: number): Promise<ContentItem> {
    return request(`/contents/${id}`);
  },

  /** 切换收藏状态 */
  toggleFavorite(id: number): Promise<{ is_favorited: boolean }> {
    return request(`/contents/${id}/favorite`, { method: 'POST' });
  },

  /** 获取收藏列表 */
  listFavorites(params?: { page?: number; page_size?: number }): Promise<PaginatedResponse<ContentItem>> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/contents/favorites/list${query}`);
  },

  /** 当日精选（自动 Top 30%） */
  todayPicks(params?: { category?: string; time_range?: string }): Promise<{
    items: ContentItem[];
    topics: TopicInfo[];
    duplicates_hidden: number;
  }> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/contents/today-picks${query}`);
  },

  /** 忽略/不感兴趣 */
  ignore(id: number, reason: string = 'not_interested'): Promise<{ content_id: number; ignored: boolean; reason: string }> {
    return request(`/contents/${id}/ignore?reason=${encodeURIComponent(reason)}`, { method: 'POST' });
  },

  /** 取消忽略 */
  unignore(id: number): Promise<{ content_id: number; ignored: boolean; removed: boolean }> {
    return request(`/contents/${id}/ignore`, { method: 'DELETE' });
  },
};

// ─── Topics API ───

// Backend returns {items: TopicGroupResponse[], total: number}
interface TopicGroupResponse {
  id: number;
  name: string;
  summary: string | null;
  keywords: string[] | null;
  content_count: number;
  best_score: number;
}

export const topicsApi = {
  /** 获取选题分组列表 */
  list(params?: TopicFilterParams): Promise<{items: TopicGroupResponse[]; total: number}> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/topics${query}`);
  },

  /** 获取选题详情（含成员内容） */
  get(id: number): Promise<{topic: TopicGroupResponse; items: Array<{id: number; title: string; url: string; source_name: string}>}> {
    return request(`/topics/${id}`);
  },

  /** 触发聚类 */
  cluster(): Promise<{status: string; stats: Record<string, unknown>}> {
    return request('/topics/cluster', { method: 'POST' });
  },
};

// ─── Analyses API ───

export const analysesApi = {
  /** 分析单条内容 */
  analyzeContent(id: number): Promise<ContentAnalysis> {
    return request(`/analyses/content/${id}`, { method: 'POST' });
  },

  /** 获取内容的分析结果 */
  getAnalysis(contentId: number): Promise<ContentAnalysis> {
    return request(`/analyses/content/${contentId}`);
  },

  /** 批量分析 */
  analyzeBatch(contentIds: number[]): Promise<ContentAnalysis[]> {
    return request('/analyses/batch', {
      method: 'POST',
      body: JSON.stringify(contentIds),
    });
  },

  /** 分析所有待处理内容 */
  analyzePending(limit: number = 20): Promise<{ message: string; count: number }> {
    return request(`/analyses/pending?limit=${limit}`, { method: 'POST' });
  },

  /** 获取分析列表 */
  list(params?: { page?: number; page_size?: number; min_creator_score?: number }): Promise<PaginatedResponse<ContentAnalysis>> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/analyses${query}`);
  },
};

// ─── Daily Report API ───

export const dailyReportApi = {
  /** 获取今日日报（不存在则自动生成） */
  getToday(): Promise<Record<string, unknown>> {
    return request('/daily-reports/today');
  },

  /** 按日期查询单个日报 */
  getByDate(date: string): Promise<Record<string, unknown>> {
    return request(`/daily-reports/by-date?date=${encodeURIComponent(date)}`);
  },

  /** 获取有日报的日期列表 */
  listDates(): Promise<{ dates: Array<{ report_date: string; weekday: string; takeaway: string | null; status: string }> }> {
    return request('/daily-reports/dates');
  },

  /** 日报列表 */
  list(limit: number = 7): Promise<{ items: Record<string, unknown>[]; total: number }> {
    return request(`/daily-reports?limit=${limit}`);
  },

  /** 强制重新生成今日日报 */
  regenerate(): Promise<Record<string, unknown>> {
    return request('/daily-reports/generate', { method: 'POST' });
  },
};

export const creationApi = {
  /** 生成创作方案 */
  generatePlan(contentId: number, platform: string): Promise<Record<string, unknown>> {
    return request('/creation/plan', {
      method: 'POST',
      body: JSON.stringify({ content_id: contentId, platform }),
    });
  },

  /** 获取可用平台列表 */
  listPlatforms(): Promise<Record<string, unknown>> {
    return request('/creation/platforms');
  },
};

// ─── Viral (低粉爆文) API ───

export const viralApi = {
  /** 获取低粉爆文列表 — 基于内容+分析数据，前端筛选排序 */
  async list(params?: {
    category?: string;
    timeRange?: string;
    sortBy?: string;
    page?: number;
    pageSize?: number;
  }): Promise<PaginatedResponse<ContentItem>> {
    // Fetch all analyzed content with high viral_score, then filter/sort client-side
    const page = params?.page || 1;
    const pageSize = params?.pageSize || 100;
    const query = '?' + new URLSearchParams(
      Object.entries({ page: String(page), page_size: String(pageSize) })
        .filter(([, v]) => v !== undefined)
    ).toString();
    return request(`/contents${query}`);
  },
};

// ─── Settings API ───

export interface RSSHubInstance {
  url: string;
  enabled: boolean;
  priority: number;
  note: string;
}

export const settingsApi = {
  /** 获取 RSSHub 实例列表 */
  getRSSHubInstances(): Promise<{ instances: RSSHubInstance[]; default_instances: string[] }> {
    return request('/settings/rsshub/instances');
  },

  /** 更新 RSSHub 实例列表 */
  updateRSSHubInstances(instances: RSSHubInstance[]): Promise<{ instances: RSSHubInstance[]; updated: boolean }> {
    return request('/settings/rsshub/instances', {
      method: 'PUT',
      body: JSON.stringify({ instances }),
    });
  },
};

// ─── Stats / Dashboard API ───

export const statsApi = {
  /** 数据统计仪表盘 */
  getDashboard(days = 7): Promise<{
    kpi: { total_crawled: number; total_curated: number; avg_curation: number; active_sources: number };
    source_breakdown: Array<{ source_name: string; source_type: string; content_count: number; curated_count: number; avg_score: number }>;
    daily_trend: Array<{ date: string; content_count: number; curated_count: number; avg_curation: number }>;
  }> {
    return request(`/stats/dashboard?days=${days}`);
  },
};

// ─── Feedback API ───

export type FeedbackType = 'like' | 'dislike' | 'skip' | 'not_relevant' | 'outdated' | 'great_pick';

export const feedbackApi = {
  /** 提交反馈 */
  submit(contentId: number, feedbackType: FeedbackType, comment?: string): Promise<Record<string, unknown>> {
    return request('/feedback', {
      method: 'POST',
      body: JSON.stringify({ content_id: contentId, feedback_type: feedbackType, comment }),
    });
  },

  /** 获取内容的反馈列表 */
  list(contentId: number): Promise<Record<string, unknown>[]> {
    return request(`/feedback/content/${contentId}`);
  },

  /** 获取反馈统计 */
  stats(): Promise<{ total: number; by_type: Record<string, number>; avg_score_delta: number }> {
    return request('/feedback/stats');
  },
};

// ─── Weekly Digest (周刊) API ───

export const weeklyDigestApi = {
  /** 获取本周周刊（不存在则自动生成） */
  getCurrent(): Promise<WeeklyDigest> {
    return request('/weekly-digests/current');
  },

  /** 按 week_key 获取周刊 */
  getByWeek(weekKey: string): Promise<WeeklyDigest> {
    return request(`/weekly-digests/by-week?week_key=${encodeURIComponent(weekKey)}`);
  },

  /** 获取所有有周刊的周列表 */
  listWeeks(): Promise<WeeklyDigestWeeksResponse> {
    return request('/weekly-digests/weeks');
  },

  /** 获取周刊列表 */
  list(limit: number = 8): Promise<WeeklyDigestListResponse> {
    return request(`/weekly-digests?limit=${limit}`);
  },

  /** 强制重新生成周刊 */
  generate(weekKey?: string): Promise<WeeklyDigest> {
    const query = weekKey ? `?week_key=${encodeURIComponent(weekKey)}` : '';
    return request(`/weekly-digests/generate${query}`, { method: 'POST' });
  },
};
