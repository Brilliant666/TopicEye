export type HotspotNewsStatus = 'ready' | 'degraded' | 'stale' | 'not_synced';
export type HotspotSourceStatus = 'healthy' | 'stale' | 'failed' | 'not_synced';

export type HotspotNewsSource = {
  key: string;
  name: string;
  homepageUrl: string;
  status: HotspotSourceStatus;
  lastSyncAt: string | null;
  itemCount: number;
  errorCode: 'source_sync_failed' | null;
};

export type HotspotNewsItem = {
  id: number;
  title: string;
  summary: string | null;
  sourceKey: string;
  sourceName: string;
  url: string;
  publishedAt: string | null;
  updatedAt: string | null;
  fetchedAt: string;
};

export type HotspotNewsResponse = {
  status: HotspotNewsStatus;
  syncedAt: string | null;
  itemCount: number;
  selectedSource: string | null;
  sources: HotspotNewsSource[];
  items: HotspotNewsItem[];
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

function validPublicUrl(value: unknown): value is string {
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

function parseSource(value: unknown): HotspotNewsSource {
  if (!record(value)
    || typeof value.key !== 'string' || value.key.length < 1
    || typeof value.name !== 'string' || value.name.length < 1
    || !validPublicUrl(value.homepageUrl)
    || !['healthy', 'stale', 'failed', 'not_synced'].includes(String(value.status))
    || !validTimestamp(value.lastSyncAt)
    || !Number.isSafeInteger(value.itemCount) || Number(value.itemCount) < 0
    || ![null, 'source_sync_failed'].includes(value.errorCode as null | string)) {
    throw new Error('rardar_hotspot_news_source_invalid');
  }
  return value as HotspotNewsSource;
}

function parseItem(value: unknown, sourceKeys: Set<string>): HotspotNewsItem {
  if (!record(value)
    || !Number.isSafeInteger(value.id) || Number(value.id) <= 0
    || typeof value.title !== 'string' || value.title.length < 1
    || !nullableString(value.summary)
    || typeof value.sourceKey !== 'string' || !sourceKeys.has(value.sourceKey)
    || typeof value.sourceName !== 'string' || value.sourceName.length < 1
    || !validPublicUrl(value.url)
    || !validTimestamp(value.publishedAt)
    || !validTimestamp(value.updatedAt)
    || !validTimestamp(value.fetchedAt, false)) {
    throw new Error('rardar_hotspot_news_item_invalid');
  }
  return value as HotspotNewsItem;
}

export function parseHotspotNewsResponse(value: unknown): HotspotNewsResponse {
  if (!record(value)
    || !['ready', 'degraded', 'stale', 'not_synced'].includes(String(value.status))
    || !validTimestamp(value.syncedAt)
    || !Number.isSafeInteger(value.itemCount) || Number(value.itemCount) < 0
    || !nullableString(value.selectedSource)
    || !Array.isArray(value.sources)
    || !Array.isArray(value.items)) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  const sources = value.sources.map(parseSource);
  const sourceKeys = new Set(sources.map((source) => source.key));
  if (sourceKeys.size !== sources.length
    || (value.selectedSource !== null && !sourceKeys.has(value.selectedSource as string))) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  const items = value.items.map((item) => parseItem(item, sourceKeys));
  if (items.length !== value.itemCount || new Set(items.map((item) => item.url)).size !== items.length) {
    throw new Error('rardar_hotspot_news_response_invalid');
  }
  return { ...value, sources, items } as HotspotNewsResponse;
}

export function filterHotspotNews(items: HotspotNewsItem[], sourceKey: string | null): HotspotNewsItem[] {
  return sourceKey ? items.filter((item) => item.sourceKey === sourceKey) : items;
}

export async function loadHotspotNews(
  fetcher: FetchLike = fetch,
  backendUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102',
): Promise<HotspotNewsLoadResult> {
  try {
    const response = await fetcher(`${backendUrl}/api/v1/rardar/hotspot-news`, {
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
