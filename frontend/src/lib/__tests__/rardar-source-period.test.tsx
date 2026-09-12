import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import RardarTrendingPage from '@/components/RardarTrendingPage';
import { beijingTime, boardPeriodLabel, type BoardSource } from '@/lib/rardar-trending';

vi.mock('@/components/RardarTodayOperations', () => ({ default: () => null }));

describe('source period and Beijing clock presentation', () => {
  it.each(['UTC', 'America/Los_Angeles', 'Asia/Tokyo'])('does not inherit host timezone %s', timezone => {
    const previous = process.env.TZ;
    process.env.TZ = timezone;
    try {
      expect(beijingTime('2026-09-11T16:00:00Z')).toBe('2026/9/12 00:00:00 北京时间');
      expect(beijingTime('2026-09-12T00:00:00Z')).toBe('2026/9/12 08:00:00 北京时间');
      expect(beijingTime('2026-09-12T08:00:00+08:00')).toBe('2026/9/12 08:00:00 北京时间');
    } finally { process.env.TZ = previous; }
  });

  it('does not invent a timezone for old naive timestamps or a full UTC day for old records', () => {
    expect(beijingTime('2026-09-12T08:00:00')).toBe('时间未知');
    expect(beijingTime('2026-09-12')).toBe('时间未知');
    expect(boardPeriodLabel({ sourceDate: '2026-09-11' })).toContain('源时区未记录');
    expect(boardPeriodLabel({ sourceDate: '2026-09-11' })).toContain('未确认完整统计窗口');
    expect(boardPeriodLabel({ sourceDate: '2026-09-11' })).not.toContain('已结束 UTC 日');
    expect(boardPeriodLabel({ sourceDate: null, acquisitionMode: 'daily_snapshot' })).toBe('源榜日期未知 · 日榜快照，未确认完整统计窗口');
  });

  it('distinguishes ended UTC source dates, successful fetch, check and local publication', () => {
    const source: BoardSource = { source: 'trendshift', label: 'Trendshift', status: 'healthy', sourceDate: '2026-09-11', sourceTimezone: 'UTC', acquisitionMode: 'ended_utc_day', periodStartAt: '2026-09-11T00:00:00Z', periodEndAt: '2026-09-12T00:00:00Z', fetchedAt: '2026-09-12T01:05:00Z', checkedAt: '2026-09-12T03:00:00Z', count: 0, errorCode: null };
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    try {
      const html = renderToStaticMarkup(<RardarTrendingPage board={{ schemaVersion: 1, generationId: 'fixture-period-only', publishedAt: '2026-09-12T01:06:00Z', checkedAt: source.checkedAt!, sources: [source], projects: [] }} />);
      expect(html).toContain('已结束 UTC 日 2026-09-11');
      expect(html).toContain('2026/9/11 08:00:00 北京时间 → 2026/9/12 08:00:00 北京时间（右端不含）');
      expect(html).toContain('成功采集 2026/9/12 09:05:00 北京时间');
      expect(html).toContain('最近检查 2026/9/12 11:00:00 北京时间');
      expect(html).toContain('本次清单发布：2026/9/12 09:06:00 北京时间');
      expect(html).not.toContain('精确 24 小时');
      expect(fetcher).not.toHaveBeenCalled();
    } finally { vi.unstubAllGlobals(); }
  });
});
