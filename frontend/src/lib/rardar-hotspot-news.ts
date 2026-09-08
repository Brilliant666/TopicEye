export type HotspotNewsStatus = 'ready' | 'degraded' | 'stale' | 'not_synced';
export type HotspotSourceStatus = 'healthy' | 'stale' | 'failed' | 'not_synced';
export type HotspotSourceKind = 'official' | 'media' | 'community' | 'aggregate';
export type HotspotContentType = 'official_update' | 'report' | 'research' | 'community_discussion' | 'uncategorized';
export type HotspotNewsSort = 'balanced' | 'latest';

export type HotspotNewsSource = {
  key: string;
  name: string;
  kind: HotspotSourceKind;
  homepageUrl: string;
  status: HotspotSourceStatus;
  lastSyncAt: string | null;
  itemCount: number;
  errorCode: 'source_sync_failed' | null;
};

export type HotspotNewsTopic = {
  key: string;
  label: string;
  itemCount: number;
};

export type HotspotNewsDiscoveryChannel = {
  key: string;
  name: string;
  kind: HotspotSourceKind;
  observedAt: string;
  discussionUrl: string | null;
  discussionAt: string | null;
  rank: number | null;
  points: number | null;
  comments: number | null;
};

export type HotspotNewsQuickRead = {
  state: 'ready' | 'title_only';
  titleZh: string;
  summaryZh: string | null;
  materialKind: 'feed_summary' | 'article_body' | 'title_only';
  generatedBy: 'ai';
  generatedAt: string;
};

export type HotspotNewsItem = {
  id: number;
  title: string;
  summary: string | null;
  sourceKey: string;
  sourceName: string;
  publisherName: string;
  url: string;
  topicKey: string;
  topicLabel: string;
  contentType: HotspotContentType;
  language: 'zh' | 'en' | 'unknown';
  publishedAt: string | null;
  updatedAt: string | null;
  fetchedAt: string;
  discoveryChannels: HotspotNewsDiscoveryChannel[];
  quickRead: HotspotNewsQuickRead | null;
};

export type HotspotNewsResponse = {
  status: HotspotNewsStatus;
  syncedAt: string | null;
  itemCount: number;
  totalItems: number;
  sourceScopeItemCount: number;
  topicScopeItemCount: number;
  page: number;
  pageSize: number;
  totalPages: number;
  sort: HotspotNewsSort;
  selectedSource: string | null;
  selectedTopic: string | null;
  sources: HotspotNewsSource[];
  topics: HotspotNewsTopic[];
  items: HotspotNewsItem[];
};

export type HotspotNewsQuery = {
  source?: string | null;
  topic?: string | null;
  sort?: HotspotNewsSort;
  page?: number;
};

export type HotspotNewsLoadResult =
  | { kind: 'published'; news: HotspotNewsResponse }
  | { kind: 'not_synced'; news: HotspotNewsResponse }
  | { kind: 'error'; code: string };

type FetchLike = typeof fetch;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function validTimestamp(value: unknown, nullable = true): value is string | null {
  if (value === null) return nullable;
  return typeof value === 'string'
    && /(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function validPublicUrl(value: unknown, nullable = false): value is string | null {
  if (value === null) return nullable;
  if (typeof value !== 'string') return false;
  try {
    const parsed = new URL(value);
    return ['http:', 'https:'].includes(parsed.protocol)
      && parsed.hostname.length > 0
      && parsed.username === ''
      && parsed.password === '';
  } catch {
    return false;
  }
}

function validCount(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function parseSource(value: unknown): HotspotNewsSource {
  if (!record(value)
    || typeof value.key !== 'string' || value.key.length < 1
    || typeof value.name !== 'string' || value.name.length < 1
    || !['official', 'media', 'community', 'aggregate'].includes(String(value.kind))
    || !validPublicUrl(value.homepageUrl)
    || !['healthy', 'stale', 'failed', 'not_synced'].includes(String(value.status))
    || !validTimestamp(value.lastSyncAt)
    || !validCount(value.itemCount)
    || ![null, 'source_sync_failed'].includes(value.errorCode as null | string)) {
    throw new Error('rardar_hotspot_news_source_invalid');
  }
  return value as HotspotNewsSource;
}

function parseTopic(value: unknown): HotspotNewsTopic {
  if (!record(value)
    || typeof value.key !== 'string' || value.key.length < 1
    || typeof value.label !== 'string' || value.label.length < 1
    || !validCount(value.itemCount)) {
    throw new Error('rardar_hotspot_news_topic_invalid');
  }
  return value as HotspotNewsTopic;
}

function nullableCount(value: unknown): value is number | null {
  return value === null || validCount(value);
}

function parseChannel(value: unknown, sourceKeys: Set<string>): HotspotNewsDiscoveryChannel {
  if (!record(value)
    || typeof value.key !== 'string' || !sourceKeys.has(value.key)
    || typeof value.name !== 'string' || value.name.length < 1
    || !['official', 'media', 'community', 'aggregate'].includes(String(value.kind))
    || !validTimestamp(value.observedAt, false)
    || !validPublicUrl(value.discussionUrl, true)
    || !validTimestamp(value.discussionAt)
    || !nullableCount(value.rank) || (typeof value.rank === 'number' && value.rank < 1)
    || !nullableCount(value.points)
    || !nullableCount(value.comments)) {
    throw new Error('rardar_hotspot_news_channel_invalid');
  }
  return value as HotspotNewsDiscoveryChannel;
}

function parseQuickRead(value: unknown): HotspotNewsQuickRead | null {
  if (value === null) return null;
  if (!record(value)
    || !['ready', 'title_only'].includes(String(value.state))
    || typeof value.titleZh !== 'string' || value.titleZh.length < 1
    || !nullableString(value.summaryZh)
    || !['feed_summary', 'article_body', 'title_only'].includes(String(value.materialKind))
    || value.generatedBy !== 'ai'
    || !validTimestamp(value.generatedAt, false)
    || (value.state === 'title_only' && value.summaryZh !== null)) {
    throw new Error('rardar_hotspot_news_quick_read_invalid');
  }
  return value as HotspotNewsQuickRead;
}

function parseItem(value: unknown, sourceKeys: Set<string>, topicKeys: Set<string>): HotspotNewsItem {
  if (!record(value)
    || !Number.isSafeInteger(value.id) || Number(value.id) <= 0
    || typeof value.title !== 'string' || value.title.length < 1
    || !nullableString(value.summary)
    || typeof value.sourceKey !== 'string' || !sourceKeys.has(value.sourceKey)
    || typeof value.sourceName !== 'string' || value.sourceName.length < 1
    || typeof value.publisherName !== 'string' || value.publisherName.length < 1
    || !validPublicUrl(value.url)
    || typeof value.topicKey !== 'string' || !topicKeys.has(value.topicKey)
    || typeof value.topicLabel !== 'string' || value.topicLabel.length < 1
    || !['official_update', 'report', 'research', 'community_discussion', 'uncategorized'].includes(String(value.contentType))
    || !['zh', 'en', 'unknown'].includes(String(value.language))
    || !validTimestamp(value.publishedAt)
    || !validTimestamp(value.updatedAt)
    || !validTimestamp(value.fetchedAt, false)
    || !Array.isArray(value.discoveryChannels)
    || value.discoveryChannels.length < 1
    || !('quickRead' in value)) {
    throw new Error('rardar_hotspot_news_item_invalid');
  }
  const channels = value.discoveryChannels.map((channel) => parseChannel(channel, sourceKeys));
  if (new Set(channels.map((channel) => channel.key)).size !== channels.length) {
    throw new Error('rardar_hotspot_news_item_invalid');
  }
  return { ...value, discoveryChannels: channels, quickRead: parseQuickRead(value.quickRead) } as HotspotNewsItem;
}

export function parseHotspotNewsResponse(value: unknown): HotspotNewsResponse {
  if (!record(value)
    || !['ready', 'degraded', 'stale', 'not_synced'].includes(String(value.status))
    || !validTimestamp(value.syncedAt)
    || !validCount(value.itemCount)
    || !validCount(value.totalItems)
    || !validCount(value.sourceScopeItemCount)
    || !validCount(value.topicScopeItemCount)
    || !Number.isSafeInteger(value.page) || Number(value.page) < 1
    || !Number.isSafeInteger(value.pageSize) || Number(value.pageSize) < 1 || Number(value.pageSize) > 40
    || !Number.isSafeInteger(value.totalPages) || Number(value.totalPages) < 1
    || !['balanced', 'latest'].includes(String(value.sort))
    || !nullableString(value.selectedSource)
    || !nullableString(value.selectedTopic)
    || !Array.isArray(value.sources)
    || !Array.isArray(value.topics)
    || !Array.isArray(value.items)) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  const sources = value.sources.map(parseSource);
  const topics = value.topics.map(parseTopic);
  const sourceKeys = new Set(sources.map((source) => source.key));
  const topicKeys = new Set(topics.map((topic) => topic.key));
  if (sourceKeys.size !== sources.length
    || topicKeys.size !== topics.length
    || (value.selectedSource !== null && !sourceKeys.has(value.selectedSource as string))
    || (value.selectedTopic !== null && !topicKeys.has(value.selectedTopic as string))) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  const items = value.items.map((item) => parseItem(item, sourceKeys, topicKeys));
  if (items.length !== value.itemCount
    || Number(value.totalItems) < items.length
    || Number(value.page) > Number(value.totalPages)
    || new Set(items.map((item) => item.url)).size !== items.length) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  return { ...value, sources, topics, items } as HotspotNewsResponse;
}

export async function loadHotspotNews(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
  query: HotspotNewsQuery = {},
): Promise<HotspotNewsLoadResult> {
  const params = new URLSearchParams();
  if (query.source) params.set('source', query.source);
  if (query.topic) params.set('topic', query.topic);
  if (query.sort) params.set('sort', query.sort);
  if (query.page && query.page > 1) params.set('page', String(query.page));
  const suffix = params.size ? `?${params}` : '';
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/hotspot-news${suffix}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return { kind: 'error', code: `rardar_hotspot_news_http_${response.status}` };
    const news = parseHotspotNewsResponse(await response.json());
    return news.status === 'not_synced' && news.items.length === 0
      ? { kind: 'not_synced', news }
      : { kind: 'published', news };
  } catch {
    return { kind: 'error', code: 'rardar_hotspot_news_unavailable' };
  }
}
