'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { T } from '@/lib/design-tokens';
import { trendingApi, type TrendingItem, type TrendingSource } from '@/lib/api';

/* ── Constants ── */

const CATEGORIES = [
  { value: '', label: '全部' },
  { value: 'hot', label: '热点' },
  { value: 'tech', label: '科技' },
  { value: 'finance', label: '财经' },
] as const;

const SOURCE_LABELS: Record<string, string> = {
  weibo: '微博', baidu: '百度', douyin: '抖音', toutiao: '头条',
  zhihu: '知乎', bilibili: 'B站', hackernews: 'HN', ithome: 'IT之家',
  juejin: '掘金', eastmoney: '东方财富',
};

const CATEGORY_COLORS: Record<string, { bg: string; color: string }> = {
  hot: { bg: '#FFF4EE', color: '#FF6B35' },
  tech: { bg: '#E6FAF5', color: '#00C9A7' },
  finance: { bg: '#FEF3C7', color: '#D97706' },
};

const TREND_ICONS: Record<string, string> = {
  up: '↑',
  down: '↓',
  new: '★',
  stable: '→',
};

/* ── Components ── */

function TrendBadge({ trend }: { trend: string | null }) {
  if (!trend || trend === 'stable') return null;
  const colors: Record<string, { bg: string; color: string }> = {
    up: { bg: '#FEE2E2', color: '#EF4444' },
    down: { bg: '#ECFDF5', color: '#059669' },
    new: { bg: '#FFF4EE', color: '#FF6B35' },
  };
  const c = colors[trend] || colors.stable;
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '1px 5px',
      borderRadius: 4, background: c.bg, color: c.color,
    }}>
      {TREND_ICONS[trend] || trend}
    </span>
  );
}

function RankNumber({ rank }: { rank: number }) {
  const isTop3 = rank <= 3;
  return (
    <div style={{
      width: 28, height: 28, borderRadius: '50%',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 12, fontWeight: 700, flexShrink: 0,
      fontFamily: T.mono,
      ...(isTop3
        ? { background: rank === 1 ? '#FF6B35' : rank === 2 ? '#FF8F65' : '#FFB899', color: '#fff' }
        : { background: T.gray100, color: T.gray500 }),
    }}>
      {rank}
    </div>
  );
}

function SourceTag({ source }: { source: string }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 500, padding: '2px 8px',
      borderRadius: 4, background: T.gray100, color: T.gray600,
      whiteSpace: 'nowrap', flexShrink: 0,
    }}>
      {SOURCE_LABELS[source] || source}
    </span>
  );
}

function CategoryTag({ category }: { category: string }) {
  const c = CATEGORY_COLORS[category] || { bg: T.gray100, color: T.gray600 };
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 6px',
      borderRadius: 4, background: c.bg, color: c.color,
      textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>
      {category}
    </span>
  );
}

/* ── Page ── */

function TrendingPage() {
  const [items, setItems] = useState<TrendingItem[]>([]);
  const [sources, setSources] = useState<TrendingSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedSource, setSelectedSource] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [itemList, srcList] = await Promise.all([
        trendingApi.list({
          category: selectedCategory || undefined,
          source: selectedSource || undefined,
          limit: 100,
        }),
        trendingApi.listSources(),
      ]);
      setItems(itemList);
      setSources(srcList.sources || []);
    } catch (e) {
      console.error('Failed to fetch trending:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, selectedSource]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      await trendingApi.syncAll();
      await fetchData();
    } catch (e) {
      console.error('Sync failed:', e);
    } finally {
      setSyncing(false);
    }
  };

  const filteredSources = selectedCategory
    ? sources.filter(s => s.category === selectedCategory)
    : sources;

  // Group items by source for display
  const groupedItems: Record<string, TrendingItem[]> = {};
  for (const item of items) {
    if (!groupedItems[item.source]) groupedItems[item.source] = [];
    groupedItems[item.source].push(item);
  }

  return (
    <div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: T.gray900, margin: 0 }}>
            趋势雷达
          </h1>
          <p style={{ fontSize: 13, color: T.gray400, margin: '4px 0 0' }}>
            多平台热搜实时榜单 · {items.length} 条
          </p>
        </div>
        <button
          onClick={handleSyncAll}
          disabled={syncing}
          style={{
            padding: '8px 20px', fontSize: 13, fontWeight: 600,
            background: syncing ? T.gray200 : T.primary, color: T.white,
            border: 'none', borderRadius: T.radiusSm, cursor: syncing ? 'wait' : 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          {syncing ? '同步中...' : '立即刷新'}
        </button>
      </div>

      {/* Category Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {CATEGORIES.map(cat => {
          const active = selectedCategory === cat.value;
          return (
            <button
              key={cat.value}
              onClick={() => { setSelectedCategory(cat.value); setSelectedSource(''); }}
              style={{
                padding: '6px 16px', fontSize: 13, fontWeight: active ? 600 : 400,
                background: active ? T.primaryLight : T.white,
                color: active ? T.primary : T.gray600,
                border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                borderRadius: 20, cursor: 'pointer', transition: 'all 0.15s ease',
              }}
            >
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Source Filter */}
      {filteredSources.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 24, flexWrap: 'wrap' }}>
          <button
            onClick={() => setSelectedSource('')}
            style={{
              padding: '4px 12px', fontSize: 12, fontWeight: !selectedSource ? 600 : 400,
              background: !selectedSource ? T.gray900 : T.white,
              color: !selectedSource ? T.white : T.gray600,
              border: `1px solid ${!selectedSource ? T.gray900 : T.gray200}`,
              borderRadius: 16, cursor: 'pointer',
            }}
          >
            全部信源
          </button>
          {filteredSources.map(s => {
            const active = selectedSource === s.source;
            return (
              <button
                key={s.source}
                onClick={() => setSelectedSource(active ? '' : s.source)}
                style={{
                  padding: '4px 12px', fontSize: 12, fontWeight: active ? 600 : 400,
                  background: active ? T.primaryLight : T.white,
                  color: active ? T.primary : T.gray600,
                  border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                  borderRadius: 16, cursor: 'pointer',
                }}
              >
                {SOURCE_LABELS[s.source] || s.source}
                <span style={{ marginLeft: 4, fontSize: 10, color: T.gray400 }}>
                  {s.count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          加载中...
        </div>
      )}

      {/* Content: grouped by source */}
      {!loading && Object.entries(groupedItems).map(([source, srcItems]) => (
        <div key={source} style={{ marginBottom: 32 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            marginBottom: 12, paddingBottom: 8,
            borderBottom: `2px solid ${T.gray100}`,
          }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: T.gray900 }}>
              {SOURCE_LABELS[source] || source}
            </span>
            <span style={{ fontSize: 11, color: T.gray400 }}>
              {srcItems.length} 条
            </span>
            {srcItems[0] && <CategoryTag category={srcItems[0].category} />}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {srcItems.map((item, idx) => (
              <a
                key={item.id}
                href={item.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 14px', borderRadius: T.radiusXs,
                  textDecoration: 'none',
                  background: idx < 3 ? T.gray50 : T.white,
                  transition: 'background 0.12s ease',
                  cursor: item.url ? 'pointer' : 'default',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = T.gray100; }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = idx < 3 ? T.gray50 : T.white; }}
              >
                <RankNumber rank={item.rank} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13.5, fontWeight: idx < 3 ? 600 : 400,
                    color: T.gray900,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {item.title}
                  </div>
                  {item.extra?.digest && (
                    <div style={{
                      fontSize: 11, color: T.gray400, marginTop: 2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {(item.extra.digest as string).slice(0, 80)}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  {item.hot_value > 0 && (
                    <span style={{
                      fontSize: 11, fontFamily: T.mono, fontWeight: 500,
                      color: item.hot_value > 100 ? T.primary : T.gray400,
                    }}>
                      {item.hot_value >= 10000
                        ? `${(item.hot_value / 10000).toFixed(1)}万`
                        : item.hot_value.toLocaleString()}
                    </span>
                  )}
                  <TrendBadge trend={item.trend} />
                </div>
              </a>
            ))}
          </div>
        </div>
      ))}

      {/* Empty */}
      {!loading && items.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          暂无趋势数据，点击右上角「立即刷新」同步
        </div>
      )}
    </div>
  );
}

export default function TrendingPageWrapper() {
  return (
    <Suspense fallback={<div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>加载中...</div>}>
      <TrendingPage />
    </Suspense>
  );
}
