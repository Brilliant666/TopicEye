import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import RardarHotspotNewsPage from '@/components/RardarHotspotNewsPage';
import {
  loadHotspotNews,
  parseHotspotNewsResponse,
  type HotspotNewsResponse,
} from '@/lib/rardar-hotspot-news';

const payload: HotspotNewsResponse = {
  status: 'degraded',
  syncedAt: '2026-09-08T04:00:00+00:00',
  itemCount: 2,
  totalItems: 22,
  sourceScopeItemCount: 22,
  topicScopeItemCount: 22,
  page: 1,
  pageSize: 18,
  totalPages: 2,
  sort: 'balanced',
  selectedSource: null,
  selectedTopic: null,
  sources: [
    {
      key: 'ars-technica',
      name: 'Ars Technica',
      kind: 'media',
      homepageUrl: 'https://arstechnica.com/',
      status: 'healthy',
      lastSyncAt: '2026-09-08T04:00:00+00:00',
      itemCount: 12,
      errorCode: null,
    },
    {
      key: 'hacker-news',
      name: 'Hacker News',
      kind: 'community',
      homepageUrl: 'https://news.ycombinator.com/',
      status: 'healthy',
      lastSyncAt: '2026-09-08T04:00:00+00:00',
      itemCount: 10,
      errorCode: null,
    },
    {
      key: 'hugging-face-blog',
      name: 'Hugging Face Blog',
      kind: 'official',
      homepageUrl: 'https://huggingface.co/blog',
      status: 'failed',
      lastSyncAt: '2026-09-08T04:00:00+00:00',
      itemCount: 0,
      errorCode: 'source_sync_failed',
    },
  ],
  topics: [
    { key: 'hardware-chips', label: '硬件与芯片', itemCount: 1 },
    { key: 'software-open-source', label: '软件与开源', itemCount: 1 },
  ],
  items: [
    {
      id: 1,
      title: 'New processor architecture reaches production',
      summary: 'The report explains the architecture and its first production system.',
      sourceKey: 'ars-technica',
      sourceName: 'Ars Technica',
      publisherName: 'Ars Technica',
      url: 'https://arstechnica.com/gadgets/example',
      topicKey: 'hardware-chips',
      topicLabel: '硬件与芯片',
      contentType: 'report',
      language: 'en',
      publishedAt: '2026-09-08T01:00:00+00:00',
      updatedAt: null,
      fetchedAt: '2026-09-08T04:00:00+00:00',
      discoveryChannels: [
        {
          key: 'ars-technica',
          name: 'Ars Technica',
          kind: 'media',
          observedAt: '2026-09-08T04:00:00+00:00',
          discussionUrl: null,
          discussionAt: null,
          rank: null,
          points: null,
          comments: null,
        },
        {
          key: 'hacker-news',
          name: 'Hacker News',
          kind: 'community',
          observedAt: '2026-09-08T04:01:00+00:00',
          discussionUrl: 'https://news.ycombinator.com/item?id=42',
          discussionAt: '2026-09-08T02:00:00+00:00',
          rank: 3,
          points: 188,
          comments: 42,
        },
      ],
      quickRead: {
        state: 'ready',
        titleZh: '新处理器架构进入生产环境',
        summaryZh: '报道介绍了该架构及首个生产系统。',
        materialKind: 'feed_summary',
        generatedBy: 'ai',
        generatedAt: '2026-09-08T04:05:00+00:00',
      },
    },
    {
      id: 2,
      title: 'A title-only compiler discussion',
      summary: null,
      sourceKey: 'hacker-news',
      sourceName: 'Hacker News',
      publisherName: 'example.com',
      url: 'https://example.com/compiler',
      topicKey: 'software-open-source',
      topicLabel: '软件与开源',
      contentType: 'community_discussion',
      language: 'en',
      publishedAt: null,
      updatedAt: null,
      fetchedAt: '2026-09-08T03:00:00+00:00',
      discoveryChannels: [
        {
          key: 'hacker-news',
          name: 'Hacker News',
          kind: 'community',
          observedAt: '2026-09-08T03:00:00+00:00',
          discussionUrl: 'https://news.ycombinator.com/item?id=43',
          discussionAt: '2026-09-08T02:30:00+00:00',
          rank: 4,
          points: 90,
          comments: 8,
        },
      ],
      quickRead: {
        state: 'title_only',
        titleZh: '一场仅有标题的编译器讨论',
        summaryZh: null,
        materialKind: 'title_only',
        generatedBy: 'ai',
        generatedAt: '2026-09-08T04:06:00+00:00',
      },
    },
  ],
};

describe('Rardar Hotspot News', () => {
  it('validates paginated source, topic and discovery-channel contracts', () => {
    expect(parseHotspotNewsResponse(payload)).toEqual(payload);
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [payload.items[0], { ...payload.items[1], url: payload.items[0].url }],
    })).toThrow('rardar_hotspot_news_response_invalid');
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [{ ...payload.items[0], publishedAt: '2026-09-08T01:00:00' }, payload.items[1]],
    })).toThrow('rardar_hotspot_news_item_invalid');
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [{ ...payload.items[0], discoveryChannels: [{ ...payload.items[0].discoveryChannels[0], key: 'unknown' }] }],
      itemCount: 1,
    })).toThrow('rardar_hotspot_news_channel_invalid');
    expect(() => parseHotspotNewsResponse({
      ...payload,
      items: [{
        ...payload.items[0],
        quickRead: { ...payload.items[0].quickRead!, state: 'title_only', summaryZh: '不允许的摘要' },
      }],
      itemCount: 1,
    })).toThrow('rardar_hotspot_news_quick_read_invalid');
  });

  it('renders reading-first organization, truthful times, discussion attribution, filters and paging', () => {
    const html = renderToStaticMarkup(<RardarHotspotNewsPage result={{ kind: 'published', news: payload }} />);
    expect(html).toContain('综合浏览');
    expect(html).toContain('多渠道科技资讯');
    expect(html).toContain('部分来源同步失败');
    expect(html).toContain('原始发布时间未知');
    expect(html).toContain('新处理器架构进入生产环境');
    expect(html).toContain('报道介绍了该架构及首个生产系统');
    expect(html).toContain('AI 中文速读');
    expect(html).toContain('仅翻译标题');
    expect(html).toContain('目前仅取得标题');
    expect(html).toContain('查看原始标题与来源摘要');
    expect(html).toContain('本页 2 条中文速读');
    expect(html).toContain('硬件与芯片');
    expect(html).toContain('科技媒体');
    expect(html).toContain('188 points');
    expect(html).toContain('href="https://news.ycombinator.com/item?id=42"');
    expect(html).toContain('href="/news?source=ars-technica"');
    expect(html).toContain('href="/news?topic=hardware-chips"');
    expect(html).toContain('href="/news?page=2"');
    expect(html).toContain('href="https://arstechnica.com/gadgets/example"');
  });

  it('loads filters, mode and page through the saved-data GET', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      ...payload,
      status: 'ready',
      selectedSource: 'ars-technica',
      selectedTopic: 'hardware-chips',
      sort: 'latest',
      page: 2,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    const result = await loadHotspotNews(fetcher as typeof fetch, 'http://backend.test', {
      source: 'ars-technica',
      topic: 'hardware-chips',
      sort: 'latest',
      page: 2,
    });
    expect(result.kind).toBe('published');
    expect(fetcher).toHaveBeenCalledWith(
      'http://backend.test/api/v1/rardar/hotspot-news?source=ars-technica&topic=hardware-chips&sort=latest&page=2',
      { cache: 'no-store', headers: { Accept: 'application/json' } },
    );
  });
});
