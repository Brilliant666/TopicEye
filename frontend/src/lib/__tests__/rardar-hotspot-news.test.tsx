import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import RardarHotspotNewsPage from '@/components/RardarHotspotNewsPage';
import {
  filterHotspotNews,
  loadHotspotNews,
  parseHotspotNewsResponse,
  type HotspotNewsResponse,
} from '@/lib/rardar-hotspot-news';

const payload: HotspotNewsResponse = {
  status: 'degraded',
  syncedAt: '2026-09-08T04:00:00+00:00',
  itemCount: 2,
  selectedSource: null,
  sources: [
    {
      key: 'github-changelog',
      name: 'GitHub Changelog',
      homepageUrl: 'https://github.blog/changelog/',
      status: 'healthy',
      lastSyncAt: '2026-09-08T04:00:00+00:00',
      itemCount: 1,
      errorCode: null,
    },
    {
      key: 'openai-news',
      name: 'OpenAI News',
      homepageUrl: 'https://openai.com/news/',
      status: 'failed',
      lastSyncAt: '2026-09-08T04:00:00+00:00',
      itemCount: 1,
      errorCode: 'source_sync_failed',
    },
  ],
  items: [
    {
      id: 1,
      title: 'GitHub changed its API contract',
      summary: 'The response now includes a documented field.',
      sourceKey: 'github-changelog',
      sourceName: 'GitHub Changelog',
      url: 'https://github.blog/changelog/example',
      publishedAt: '2026-09-08T01:00:00+00:00',
      updatedAt: null,
      fetchedAt: '2026-09-08T04:00:00+00:00',
    },
    {
      id: 2,
      title: 'A title-only announcement',
      summary: null,
      sourceKey: 'openai-news',
      sourceName: 'OpenAI News',
      url: 'https://openai.com/news/example',
      publishedAt: null,
      updatedAt: null,
      fetchedAt: '2026-09-08T03:00:00+00:00',
    },
  ],
};

describe('Rardar Hotspot News', () => {
  it('validates saved data, source identity, timestamps, and URL uniqueness', () => {
    expect(parseHotspotNewsResponse(payload)).toEqual(payload);
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [payload.items[0], { ...payload.items[1], url: payload.items[0].url }],
    })).toThrow('rardar_hotspot_news_response_invalid');
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [{ ...payload.items[0], publishedAt: '2026-09-08T01:00:00' }, payload.items[1]],
    })).toThrow('rardar_hotspot_news_item_invalid');
  });

  it('filters by exact source key without changing the saved timeline', () => {
    expect(filterHotspotNews(payload.items, null)).toHaveLength(2);
    expect(filterHotspotNews(payload.items, 'github-changelog')).toEqual([payload.items[0]]);
    expect(payload.items).toHaveLength(2);
  });

  it('renders factual time labels, degraded state, title-only honesty, and original links', () => {
    const html = renderToStaticMarkup(<RardarHotspotNewsPage result={{ kind: 'published', news: payload }} />);
    expect(html).toContain('技术资讯时间线');
    expect(html).toContain('这不是“全网最热”排名');
    expect(html).toContain('英文条目首版保留原文');
    expect(html).toContain('部分来源同步失败');
    expect(html).toContain('发布时间未知');
    expect(html).toContain('Feed 未提供可验证摘要');
    expect(html).toContain('href="https://github.blog/changelog/example"');
    expect(html).toContain('target="_blank"');
  });

  it('loads through a saved-data GET with no request body or cache reuse', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ ...payload, status: 'ready' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    const result = await loadHotspotNews(fetcher as typeof fetch, 'http://backend.test');
    expect(result.kind).toBe('published');
    expect(fetcher).toHaveBeenCalledWith(
      'http://backend.test/api/v1/rardar/hotspot-news',
      { cache: 'no-store', headers: { Accept: 'application/json' } },
    );
  });
});
