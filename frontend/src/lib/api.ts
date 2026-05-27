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

export type { ContentItem, CreateSourceRequest, UpdateSourceRequest };
export type FeedbackType = 'like' | 'dislike' | 'skip' | 'not_relevant' | 'outdated' | 'great_pick';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

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
    const errorText = await response.text().catch(() => '');
    let error: { detail?: unknown; message?: string } = { message: response.statusText };
    if (errorText) {
      try {
        error = JSON.parse(errorText);
      } catch {
        error = { message: errorText };
      }
    }
    const detail = typeof error.detail === 'string' ? error.detail : undefined;
    throw new Error(detail || error.message || `API Error: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

// ─── Sources API ───

export const sourcesApi = {
  /** 获取信源列表（支持分页和筛选） */
  list(params?: {
    page?: number;
    page_size?: number;
    source_type?: string;
    status?: string;
    enabled?: boolean;
    keyword?: string;
  }): Promise<PaginatedResponse<Source> & { total?: number }> {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.page_size) qs.set('page_size', String(params.page_size));
    if (params?.source_type) qs.set('source_type', params.source_type);
    if (params?.status) qs.set('status', params.status);
    if (params?.enabled !== undefined) qs.set('enabled', String(params.enabled));
    if (params?.keyword) qs.set('keyword', params.keyword);
    const query = qs.toString();
    return request(`/sources${query ? '?' + query : ''}`);
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

  /** 保存信源排序（用于信源地图看板拖拽） */
  reorder(ordered_ids: number[]): Promise<{ message: string; updated: number }> {
    return request('/sources/reorder', {
      method: 'POST',
      body: JSON.stringify({ ordered_ids }),
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

  scoringFlow(params?: { hours?: number; limit?: number }): Promise<ScoringFlowResponse> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/contents/scoring-flow${query}`);
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

export interface ScoringFlowStage {
  key: string;
  label: string;
  count: number;
  retention: number;
}

export interface ScoringFlowSample {
  id: number;
  title: string;
  url: string;
  source_name: string | null;
  category: string;
  selected: boolean;
  final_score: number;
  threshold_used: number;
  base_score: number;
  source_bonus: number;
  quality_factor: number;
  risk_factor: number;
  time_decay: number;
  diversity_factor: number;
  feedback_score: number;
  dimension_scores: Record<string, number>;
}

export interface ScoringFlowResponse {
  total: number;
  scored: number;
  hours: number;
  stages: ScoringFlowStage[];
  samples: ScoringFlowSample[];
  category_mix: Array<{ label: string; count: number }>;
  source_mix: Array<{ label: string; count: number }>;
}

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

  /** 获取最近一段时间的日报状态地图 */
  calendar(days: number = 30): Promise<{
    days: Array<{
      report_date: string;
      weekday: string;
      status: string;
      edition: string | null;
      generated_at: string | null;
      cutoff_at: string | null;
      takeaway: string | null;
      content_count: number;
      analyzed_count: number;
      topic_count: number;
      has_report: boolean;
      can_generate: boolean;
      is_today: boolean;
    }>;
    total_days: number;
    done_count: number;
    error_count: number;
    missing_count: number;
    generating_count: number;
  }> {
    return request(`/daily-reports/calendar?days=${days}`);
  },

  /** 日报列表 */
  list(limit: number = 7): Promise<{ items: Record<string, unknown>[]; total: number }> {
    return request(`/daily-reports?limit=${limit}`);
  },

  /** 强制重新生成今日日报 */
  regenerate(): Promise<Record<string, unknown>> {
    return request('/daily-reports/generate', { method: 'POST' });
  },

  /** 生成指定日报版本 */
  generateVersion(params: { target_date?: string; edition?: string; cutoff_at?: string; force?: boolean } = {}): Promise<Record<string, unknown>> {
    const query = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return request(`/daily-reports/generate-version${query ? `?${query}` : ''}`, { method: 'POST' });
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
  /** 获取低粉爆文列表 */
  async list(params?: {
    category?: string;
    hours?: number;
    sort_by?: string;
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<ContentItem> & { total?: number }> {
    const page = params?.page || 1;
    const pageSize = params?.page_size || 20;
    const query = '?' + new URLSearchParams(
      Object.entries({
        page: String(page),
        page_size: String(pageSize),
        sort_by: 'low_follower_viral',
        hours: params?.hours !== undefined ? String(params.hours) : '',
        category: params?.category || '',
      }).filter(([, v]) => v !== '') as [string, string][]
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

export interface StatsOverview {
  total: number;
  analyzed: number;
  curated: number;
  today_new: number;
}

export interface StatsSourceItem {
  source_name: string;
  source_type: string;
  content_count: number;
  curated_count: number;
  curation_rate: number;
}

export interface StatsCategoryItem {
  category: string;
  content_count: number;
  avg_score: number;
}

export interface StatsTrendItem {
  date: string;
  content_count: number;
  curated_count: number;
  analyzed_count: number;
}

export interface StatsNovelPlatform {
  name: string;
  table: string;
  count: number;
  last_sync: string | null;
}

export const statsApi = {
  /** 内容总览 */
  getOverview(days = 7): Promise<StatsOverview> {
    return request(`/stats/overview?days=${days}`);
  },

  /** 信源分布 */
  getSourceDistribution(days = 7): Promise<{ sources: StatsSourceItem[] }> {
    return request(`/stats/source-distribution?days=${days}`);
  },

  /** 分类分布 */
  getCategoryDistribution(days = 7): Promise<{ categories: StatsCategoryItem[] }> {
    return request(`/stats/category-distribution?days=${days}`);
  },

  /** 时间趋势 */
  getDailyTrend(days = 7): Promise<{ trend: StatsTrendItem[] }> {
    return request(`/stats/daily-trend?days=${days}`);
  },

  /** 网文平台统计 */
  getNovelPlatforms(): Promise<{ platforms: StatsNovelPlatform[] }> {
    return request('/stats/novel-platforms');
  },

  /** Legacy dashboard (backward compat) */
  getDashboard(days = 7): Promise<{
    kpi: { total_crawled: number; total_curated: number; avg_curation: number; active_sources: number };
    source_breakdown: Array<{ source_name: string; source_type: string; content_count: number; curated_count: number; avg_score: number }>;
    daily_trend: Array<{ date: string; content_count: number; curated_count: number; avg_curation: number }>;
  }> {
    return request(`/stats/dashboard?days=${days}`);
  },
};

// ─── Feedback API ───

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

// ─── Trending Radar (趋势雷达) API ───

export interface TrendingItem {
  id: number;
  source: string;
  category: string;
  rank: number;
  title: string;
  url: string;
  hot_value: number;
  hot_value_raw: string;
  trend: string | null;
  cover_url: string | null;
  extra: Record<string, unknown> | null;
  fetched_at: string;
  batch_id: string;
}

export interface TrendingSource {
  source: string;
  category: string;
  display_name: string;
  count: number;
  last_synced: string | null;
}

export const trendingApi = {
  /** 获取趋势数据 */
  list(params?: { category?: string; source?: string; limit?: number }): Promise<TrendingItem[]> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/trending${query}`);
  },

  /** 获取可用信源列表 */
  listSources(): Promise<{ sources: TrendingSource[] }> {
    return request('/trending/sources');
  },

  /** 同步单个信源 */
  sync(source: string): Promise<{ fetched: number }> {
    return request(`/trending/sync/${source}`, { method: 'POST' });
  },

  /** 同步所有信源 */
  syncAll(): Promise<Record<string, { fetched: number }>> {
    return request('/trending/sync-all', { method: 'POST' });
  },

  /** 跨平台热点交叉发现 */
  crossPlatform(params?: { min_resonance?: number; limit?: number }): Promise<{
    total: number;
    clusters: CrossPlatformCluster[];
  }> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/trending/cross-platform${query}`);
  },

  /** 持续在榜话题分析 */
  persistent(params?: { min_days?: number; min_sources?: number; days_back?: number }): Promise<{
    total: number;
    topics: PersistentTopic[];
  }> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/trending/persistent${query}`);
  },
};

// ─── Cross-Platform Clustering ───

export interface PersistentTopic {
  title: string;
  days_on_list: number;
  total_days: number;
  snapshot_count: number;
  sources: string[];
  source_count: number;
  avg_rank: number;
  best_rank: number;
  hot_value_max: number;
  rank_trend: number[];
  first_seen: string;
  last_seen: string;
}

export interface CrossPlatformSourceItem {
  source: string;
  source_label: string;
  title: string;
  rank: number;
  hot_value: number;
  hot_value_raw: string;
  url: string;
  trend: string | null;
}

export interface CrossPlatformCluster {
  topic: string;
  keywords: string[];
  resonance: number;
  item_count: number;
  sources: string[];
  source_labels: string[];
  source_items: CrossPlatformSourceItem[];
  total_hot: number;
  avg_rank: number;
}

// ─── Mother Topics API ──────────────────────────────────────────────

export interface MotherTopic {
  id: number;
  name: string;
  description: string | null;
  keywords: string[];
  weight: number;
  content_type: string | null;
  target_reader: string | null;
  is_active: boolean;
  display_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export type MotherTopicMutation = Partial<
  Pick<
    MotherTopic,
    | 'name'
    | 'description'
    | 'keywords'
    | 'weight'
    | 'content_type'
    | 'target_reader'
    | 'is_active'
    | 'display_order'
  >
>;

export interface ContentScoringResult {
  title: string;
  topic_scores: Array<{
    name: string;
    keyword_score: number;
    weight: number;
    freshness: number;
    final: number;
  }>;
  top_topic: string | null;
  final_score: number;
}

export const motherTopicsApi = {
  /** 列出所有母题 */
  list(active_only = false): Promise<MotherTopic[]> {
    return request(`/mother-topics/?active_only=${active_only}`);
  },

  /** 创建母题 */
  create(data: {
    name: string;
    description?: string;
    keywords: string[];
    weight?: number;
    content_type?: string;
    target_reader?: string;
    is_active?: boolean;
    display_order?: number;
  }): Promise<MotherTopic> {
    return request('/mother-topics/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** 更新母题 */
  update(
    id: number,
    data: MotherTopicMutation
  ): Promise<MotherTopic> {
    return request(`/mother-topics/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** 删除母题（软删除） */
  delete(id: number): Promise<{ ok: boolean; message: string }> {
    return request(`/mother-topics/${id}`, { method: 'DELETE' });
  },

  /** 对内容按母题打分 */
  score(data: {
    title: string;
    summary?: string;
    source?: string;
    hot_value?: number;
  }): Promise<ContentScoringResult> {
    return request('/mother-topics/score', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** 批量对多条内容按母题打分（只查一次 DB） */
  scoreBatch(items: Array<{
    title: string;
    summary?: string;
    hot_value?: number;
  }>): Promise<{ results: ContentScoringResult[] }> {
    return request('/mother-topics/score-batch', {
      method: 'POST',
      body: JSON.stringify({ items }),
    });
  },

  /** 对已入库内容重新匹配母题 */
  matchContent(contentId: number): Promise<{
    content_id: number;
    title: string;
    top_topic: string | null;
    top_score: number;
    all_scores: Array<{ name: string; keyword_score: number; weight: number; final: number }>;
  }> {
    return request(`/mother-topics/match/${contentId}`);
  },
};

/* ── 番茄小说 ── */

export interface FanqieCategory {
  fanqie_id: string;
  name: string;
  group: 'male' | 'female';
}

export interface FanqieBook {
  book_id: string;
  url: string;
  book_name: string;
  author: string;
  abstract: string;
  thumb_uri: string;
  read_count: string;
  word_number: string;
  last_chapter_title: string;
  position: number;
  rank_type: string;
  rank_pos_diff?: number | null;
}

export const fanqieApi = {
  /** 获取全部分类 */
  categories(): Promise<FanqieCategory[]> {
    return request('/fanqie/categories');
  },

  /** 获取四大榜单（或指定类型） */
  rankings(type?: string): Promise<Record<string, {
    label: string;
    count: number;
    books: FanqieBook[];
  }>> {
    const params = type ? `?type=${type}` : '';
    return request(`/fanqie/rankings${params}`);
  },

  /** 获取分类下图书 */
  categoryBooks(
    fanqieId: string,
    params?: { rank_type?: string; limit?: number },
  ): Promise<{ fanqie_id: string; count: number; books: FanqieBook[] }> {
    const qs = new URLSearchParams();
    if (params?.rank_type) qs.set('rank_type', params.rank_type);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return request(`/fanqie/category/${fanqieId}/books${query ? '?' + query : ''}`);
  },

  /** 手动触发全量同步 */
  sync(): Promise<{ categories: number; elapsed_seconds: number }> {
    return request('/fanqie/sync', { method: 'POST' });
  },
};

// ─── 知乎盐选 API ──────────────────────────────────...

// ─── 七猫小说 API ────────────────────────────────────────────────────────────

export interface QimaoBook {
  book_id: string;
  url: string;
  title: string;
  author: string;
  abstract: string;
  category1_name: string;
  category2_name: string;
  thumb_uri: string;
  words_num: string;
  collect_count: number;
  latest_chapter_title: string;
  update_time: string;
  is_over: number;
  is_continue_top: number;
  index_change: number;
  position: number;
  rank_type?: string;
}

export const qimaoApi = {
  list(channel: string, rankType: string, limit = 20, offset = 0): Promise<{
    channel: string; rank_type: string; count: number;
    books: QimaoBook[];
  }> {
    const qs = new URLSearchParams({ channel, rank_type: rankType, limit: String(limit), offset: String(offset) });
    return request(`/qimao/books?${qs}`);
  },
  sync(): Promise<{ books: number; elapsed_seconds: number }> {
    return request('/qimao/sync', { method: 'POST' });
  },
};

// ─── 知乎盐选 API ────────────────────────────────────────────────────────────

export interface ZhihuAlbum {
  business_id: string;
  title: string;
  author: string;
  author_desc: string | null;
  abstract: string | null;
  thumb_url: string | null;
  chapter_text: string | null;
  price_yuan: string;
  price: number;
  is_exclusive: boolean;
  is_svip: boolean;
  online_time_text: string | null;
  tag: string | null;
  category1_name: string;
  category2_name: string | null;
  position: number;
  rank_pos_diff: number | null;
  url: string;
  sort_type: string;
}

export interface ZhihuCategory {
  zhihu_id: string;
  name: string;
  name_en: string | null;
  level: number;
  parent_id: string | null;
  sort: number;
  artwork: string | null;
}

export const zhihuApi = {
  list(sortType = 'hottest', category?: string, subcategory?: string, limit = 20, offset = 0): Promise<{
    sort_type: string; category: string; count: number; total: number;
    albums: ZhihuAlbum[];
  }> {
    const qs = new URLSearchParams({ sort_type: sortType, limit: String(limit), offset: String(offset) });
    if (category) qs.set('category', category);
    if (subcategory) qs.set('subcategory', subcategory);
    return request(`/zhihu/albums?${qs}`);
  },
  categories(parentId?: string): Promise<{ count: number; categories: ZhihuCategory[] }> {
    const qs = parentId ? `?parent_id=${parentId}` : '';
    return request(`/zhihu/categories${qs}`);
  },
  sync(): Promise<{ status: string; message: string }> {
    return request('/zhihu/sync', { method: 'POST' });
  },
};

// ─── LLM Models API ───

export interface LlmModelItem {
  id: number;
  name: string;
  provider: string;
  model_id: string;
  api_base: string | null;
  api_key_set: boolean;
  enabled: boolean;
  is_primary: boolean;
  is_fallback: boolean;
  temperature: number;
  max_tokens: number;
  requests_per_minute: number;
  description: string | null;
  cost_per_1k_input: number | null;
  cost_per_1k_output: number | null;
  extra_params: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EvalRun {
  eval_run_id: string;
  prompt_type: string;
  model_count: number;
  created_at: string | null;
  done_count: number;
  fail_count: number;
}

export interface EvalResult {
  id: number;
  model_id: number;
  model_name: string;
  status: string;
  response_text: string | null;
  duration_ms: number;
  tokens_input: number | null;
  tokens_output: number | null;
  quality_score: number | null;
  auto_score: number | null;
  notes: string | null;
  error_message: string | null;
  created_at: string | null;
}

export interface ModelUsageBucket {
  calls: number;
  success_calls: number;
  failed_calls: number;
  tokens_input: number;
  tokens_output: number;
  estimated_cost: number;
}

export interface ModelUsageByModel extends ModelUsageBucket {
  model_id: number;
  model_name: string;
  provider: string | null;
  avg_duration_ms: number;
  cost_per_1k_input: number | null;
  cost_per_1k_output: number | null;
}

export interface ModelUsageByPrompt extends ModelUsageBucket {
  prompt_type: string;
}

export interface ModelUsageSummary {
  days: number;
  since: string;
  total: ModelUsageBucket & {
    tokens_total: number;
    avg_duration_ms: number;
    success_rate: number;
  };
  by_model: ModelUsageByModel[];
  by_prompt: ModelUsageByPrompt[];
}

export const modelsApi = {
  list(): Promise<{ models: LlmModelItem[]; total: number }> {
    return request('/models');
  },
  usageSummary(days = 30): Promise<ModelUsageSummary> {
    return request(`/models/usage/summary?days=${days}`);
  },
  create(data: Partial<LlmModelItem> & { api_key?: string }): Promise<{ id: number; name: string; message: string }> {
    return request('/models', { method: 'POST', body: JSON.stringify(data) });
  },
  update(id: number, data: Partial<LlmModelItem> & { api_key?: string }): Promise<{ message: string }> {
    return request(`/models/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },
  delete(id: number): Promise<{ message: string }> {
    return request(`/models/${id}`, { method: 'DELETE' });
  },
  setPrimary(id: number): Promise<{ message: string }> {
    return request(`/models/${id}/set-primary`, { method: 'POST' });
  },
  setFallback(id: number): Promise<{ message: string }> {
    return request(`/models/${id}/set-fallback`, { method: 'POST' });
  },
  test(id: number): Promise<{ status: string; model_name: string; response?: string; error?: string; duration_ms: number; tokens_input?: number; tokens_output?: number }> {
    return request(`/models/${id}/test`, { method: 'POST' });
  },
  runEvaluation(data: { model_ids: number[]; prompt_type: string; custom_prompt?: string; sample_content?: string }): Promise<{ eval_run_id: string; model_count: number; message: string }> {
    return request('/models/evaluations/run', { method: 'POST', body: JSON.stringify(data) });
  },
  listEvalRuns(limit?: number): Promise<{ runs: EvalRun[]; total: number }> {
    const qs = limit ? `?limit=${limit}` : '';
    return request(`/models/evaluations/runs${qs}`);
  },
  getEvalRun(runId: string): Promise<{ eval_run_id: string; prompt_type: string; results: EvalResult[] }> {
    return request(`/models/evaluations/runs/${runId}`);
  },
  scoreEvaluation(evalId: number, quality_score: number, notes?: string): Promise<{ message: string }> {
    return request(`/models/evaluations/${evalId}/score`, { method: 'PUT', body: JSON.stringify({ quality_score, notes }) });
  },
};
