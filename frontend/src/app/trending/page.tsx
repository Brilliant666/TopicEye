'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { Lightbulb } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import {
  trendingApi,
  type TrendingItem,
  type TrendingSource,
  type CrossPlatformCluster,
  type CrossPlatformSourceItem,
  type PersistentTopic,
} from '@/lib/api';

/* ── Global scrollbar style (injected once) ── */
if (typeof document !== 'undefined' && !document.getElementById('trending-scrollbar-css')) {
  const style = document.createElement('style');
  style.id = 'trending-scrollbar-css';
  style.textContent = `
    .trending-scroll::-webkit-scrollbar { width: 5px; }
    .trending-scroll::-webkit-scrollbar-track { background: transparent; }
    .trending-scroll::-webkit-scrollbar-thumb { background: ${T.gray300}; border-radius: 4px; }
    .trending-scroll::-webkit-scrollbar-thumb:hover { background: ${T.gray400}; }
  `;
  document.head.appendChild(style);
}

/* ── Constants ── */

const CATEGORIES = [
  { value: '', label: '全部' },
  { value: 'hot', label: '热点' },
  { value: 'tech', label: '科技' },
  { value: 'finance', label: '财经' },
] as const;

const SOURCE_BRAND: Record<string, { label: string; color: string; bg: string }> = {
  weibo:       { label: '微博',     color: '#FF8200', bg: '#FFF7EB' },
  baidu:       { label: '百度',     color: '#306CFF', bg: '#EBF1FF' },
  douyin:      { label: '抖音',     color: '#161823', bg: '#F5F5F7' },
  toutiao:     { label: '头条',     color: '#F85959', bg: '#FFF0F0' },
  zhihu:       { label: '知乎',     color: '#0066FF', bg: '#EBF2FF' },
  bilibili:    { label: 'B站',      color: '#FB7299', bg: '#FFF0F5' },
  hackernews:  { label: 'HN',       color: '#FF6600', bg: '#FFF5EB' },
  ithome:      { label: 'IT之家',   color: '#D22222', bg: '#FFF0F0' },
  juejin:      { label: '掘金',     color: '#1E80FF', bg: '#EBF3FF' },
  eastmoney:   { label: '东方财富', color: '#D4940A', bg: '#FFF8E8' },
  douban:      { label: '豆瓣',     color: '#00B51D', bg: '#EEFBF0' },
  tieba:       { label: '贴吧',     color: '#4E6EF2', bg: '#EEF1FD' },
  netease:     { label: '网易',     color: '#C03A3A', bg: '#FDF0F0' },
  v2ex:        { label: 'V2EX',     color: '#333333', bg: '#F0F0F0' },
  github:      { label: 'GitHub',   color: '#24292F', bg: '#F0F1F3' },
  sspai:       { label: '少数派',   color: '#D6192B', bg: '#FDF0F0' },
  xueqiu:      { label: '雪球',     color: '#1478FF', bg: '#ECF3FF' },
  sohu:        { label: '搜狐',     color: '#D8503C', bg: '#FDF0EF' },
  hupu:        { label: '虎扑',     color: '#D43030', bg: '#FDF0F0' },
  kr36:        { label: '36氪',     color: '#0080FF', bg: '#ECF3FF' },
};

function sourceBrand(source: string) {
  return SOURCE_BRAND[source] || { label: source, color: T.gray600, bg: T.gray100 };
}

const SOURCE_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(SOURCE_BRAND).map(([k, v]) => [k, v.label])
);

const CATEGORY_COLORS: Record<string, { bg: string; color: string }> = {
  hot: { bg: '#FFF4EE', color: '#FF6B35' },
  tech: { bg: '#E6FAF5', color: '#00C9A7' },
  finance: { bg: '#FEF3C7', color: '#D97706' },
};

const TREND_ICONS: Record<string, string> = {
  up: '↑', down: '↓', new: '★', stable: '→',
};

const RESONANCE_COLORS: Record<number, { bg: string; color: string; label: string }> = {
  5: { bg: '#FEE2E2', color: '#EF4444', label: '超强共振' },
  4: { bg: '#FFECB5', color: '#D97706', label: '强共振' },
  3: { bg: '#FEF9C3', color: '#A16207', label: '共振' },
  2: { bg: '#E6FAF5', color: '#059669', label: '轻微' },
};

/* ── Components ── */

function TrendBadge({ trend }: { trend: string | null }) {
  if (!trend || trend === 'stable') return null;
  const colors: Record<string, { bg: string; color: string }> = {
    up: { bg: '#FEE2E2', color: '#EF4444' },
    down: { bg: '#ECFDF5', color: '#059669' },
    new: { bg: '#FFF4EE', color: '#FF6B35' },
  };
  const c = colors[trend] || { bg: T.gray100, color: T.gray600 };
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

/* ── 共振话题卡片 ── */

function ResonanceBadge({ resonance }: { resonance: number }) {
  const c = RESONANCE_COLORS[resonance] || RESONANCE_COLORS[2];
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: '2px 8px',
      borderRadius: 6, background: c.bg, color: c.color,
      whiteSpace: 'nowrap',
    }}>
      {c.label} · {resonance}平台
    </span>
  );
}

function HotValue({ value }: { value: number }) {
  if (!value) return null;
  return (
    <span style={{
      fontSize: 11, fontFamily: T.mono, fontWeight: 500,
      color: value > 10000 ? T.primary : T.gray400,
    }}>
      {value >= 10000 ? `${(value / 10000).toFixed(1)}万` : value.toLocaleString()}
    </span>
  );
}

function SourceMiniItem({ item }: { item: CrossPlatformSourceItem }) {
  return (
    <a
      href={item.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: T.radiusXs,
        textDecoration: 'none',
        background: T.white,
        border: `1px solid ${T.gray100}`,
        transition: 'all 0.12s ease',
        flex: 1, minWidth: 0,
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLAnchorElement;
        el.style.borderColor = T.primaryBorder;
        el.style.background = T.primaryLight;
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLAnchorElement;
        el.style.borderColor = T.gray100;
        el.style.background = T.white;
      }}
    >
      <span style={{
        fontSize: 10, fontWeight: 600,
        color: item.rank <= 3 ? '#FF6B35' : T.gray400,
        minWidth: 16,
      }}>
        #{item.rank}
      </span>
      <span style={{
        fontSize: 12, color: T.gray700,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        flex: 1,
      }}>
        {item.title}
      </span>
      <span style={{ fontSize: 10, color: T.gray400, flexShrink: 0 }}>
        {SOURCE_LABELS[item.source] || item.source}
      </span>
    </a>
  );
}

/* ── 角度推荐面板 ── */

interface AngleResult {
  common_angles: string[];
  contrast_angles: { angle: string; reasoning: string }[];
  angle_note: string;
}

function AnglePanel({ cluster }: { cluster: CrossPlatformCluster }) {
  const [angles, setAngles] = useState<AngleResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetchAngles = async () => {
    if (fetched || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/trending/angles?topic=${encodeURIComponent(cluster.topic)}`
      );
      if (!res.ok) throw new Error('请求失败');
      const data = await res.json();
      setAngles(data);
      setFetched(true);
    } catch (e) {
      setError('角度生成失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      marginTop: 8,
      padding: '10px 14px',
      background: '#FFFBEB',
      border: `1px solid #FDE68A`,
      borderRadius: T.radiusSm,
    }}>
      {/* 按钮行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: '#92400E' }}>AI 角度推荐</span>
        {!fetched && !loading && (
          <button
            onClick={fetchAngles}
            style={{
              fontSize: 10, fontWeight: 600,
              padding: '2px 8px', borderRadius: 8,
              background: '#F59E0B', color: '#fff',
              border: 'none', cursor: 'pointer',
            }}
          >
            生成反差角度
          </button>
        )}
        {loading && (
          <span style={{ fontSize: 10, color: '#92400E' }}>生成中...</span>
        )}
      </div>

      {/* 大众角度（不要写） */}
      {angles && angles.common_angles.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: '#92400E', marginBottom: 4, fontWeight: 600 }}>
            大众角度（不要写）：
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {angles.common_angles.map((a, i) => (
              <span key={i} style={{
                fontSize: 10, color: '#78350F',
                background: '#FEF3C7',
                padding: '2px 6px', borderRadius: 6,
                textDecoration: 'line-through',
              }}>{a}</span>
            ))}
          </div>
        </div>
      )}

      {/* 反差角度 */}
      {angles && angles.contrast_angles.length > 0 && (
        <div>
          <div style={{ fontSize: 10, color: '#065F46', marginBottom: 4, fontWeight: 600 }}>
            反差角度（值得写）：
          </div>
          {angles.contrast_angles.map((c, i) => (
            <div key={i} style={{
              marginBottom: 6,
              padding: '6px 10px',
              background: '#ECFDF5',
              borderRadius: T.radiusXs,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#065F46', marginBottom: 2 }}>
                → {c.angle}
              </div>
              <div style={{ fontSize: 10, color: '#047857' }}>
                {c.reasoning}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 角度洞察 */}
      {angles && angles.angle_note && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 6,
          marginTop: 6, padding: '4px 8px',
          background: '#F0FDF4', borderRadius: T.radiusXs,
          fontSize: 10, color: '#166534',
          fontStyle: 'italic',
        }}>
          <Lightbulb size={12} strokeWidth={2} style={{ marginTop: 1, flexShrink: 0 }} />
          <span>{angles.angle_note}</span>
        </div>
      )}

      {error && (
        <div style={{ fontSize: 10, color: '#DC2626' }}>{error}</div>
      )}
    </div>
  );
}

/* ── 展开后的完整 ClusterCard ── */

function ClusterCardExpanded({ cluster }: { cluster: CrossPlatformCluster }) {
  return (
    <>
      {/* 平台详情 */}
      <div style={{
        fontSize: 11, fontWeight: 600, color: T.gray500,
        marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        各平台排名
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {cluster.source_items.map(item => (
          <SourceMiniItem key={`${item.source}-${item.rank}`} item={item} />
        ))}
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 10, paddingTop: 8, borderTop: `1px dashed ${T.gray200}`,
      }}>
        <span style={{ fontSize: 11, color: T.gray400 }}>
          平均排名 #{cluster.avg_rank} · {cluster.total_hot.toLocaleString()} 总热度
        </span>
        <a
          href={cluster.source_items[0]?.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: 11, color: T.primary, textDecoration: 'none',
            fontWeight: 600,
          }}
        >
          查看详情 →
        </a>
      </div>

      {/* AI 角度推荐 */}
      <AnglePanel cluster={cluster} />
    </>
  );
}

function ClusterCard({ cluster }: { cluster: CrossPlatformCluster }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      overflow: 'hidden',
      transition: 'box-shadow 0.15s ease',
    }}>
      {/* 卡片头部 */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: '14px 16px',
          cursor: 'pointer',
          background: expanded ? T.gray50 : T.white,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          {/* 左侧：共振强度标识 */}
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: RESONANCE_COLORS[cluster.resonance]?.bg || T.gray100,
            color: RESONANCE_COLORS[cluster.resonance]?.color || T.gray500,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 16, fontWeight: 800, lineHeight: 1 }}>{cluster.resonance}</span>
            <span style={{ fontSize: 8, fontWeight: 600, marginTop: 2 }}>平台</span>
          </div>

          {/* 中间：标题+关键词 */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 600, color: T.gray900,
              lineHeight: 1.4,
              overflow: 'hidden', textOverflow: 'ellipsis',
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
            }}>
              {cluster.topic}
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
              {cluster.keywords.slice(0, 4).map(kw => (
                <span key={kw} style={{
                  fontSize: 10, color: T.gray500,
                  background: T.gray100,
                  padding: '1px 6px', borderRadius: 4,
                }}>#{kw}</span>
              ))}
            </div>
          </div>

          {/* 右侧：平台标签+展开按钮 */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
            <ResonanceBadge resonance={cluster.resonance} />
            <span style={{ fontSize: 11, color: T.gray400 }}>
              {expanded ? '收起↑' : '展开↓'}
            </span>
          </div>
        </div>

        {/* 平台横向滚动条 */}
        <div style={{
          display: 'flex', gap: 6, marginTop: 10, overflowX: 'auto',
          paddingBottom: 4,
        }}>
          {cluster.source_labels.map((label, i) => (
            <span key={i} style={{
              fontSize: 10, fontWeight: 500,
              padding: '2px 7px', borderRadius: 12,
              background: T.gray100, color: T.gray600,
              whiteSpace: 'nowrap', flexShrink: 0,
            }}>
              {label}
            </span>
          ))}
          <span style={{ fontSize: 10, color: T.gray400, marginLeft: 4, flexShrink: 0 }}>
            {cluster.item_count}条相关内容
          </span>
        </div>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div style={{
          padding: '10px 16px 14px',
          background: T.gray50,
          borderTop: `1px solid ${T.gray100}`,
        }}>
          <ClusterCardExpanded cluster={cluster} />
        </div>
      )}
    </div>
  );
}

/* ── Helpers ── */

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}小时前`;
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return '';
  }
}

/* ── Page ── */

function TrendingPage() {
  const [tab, setTab] = useState<'list' | 'resonance' | 'persistent'>('list');
  const [items, setItems] = useState<TrendingItem[]>([]);
  const [sources, setSources] = useState<TrendingSource[]>([]);
  const [clusters, setClusters] = useState<CrossPlatformCluster[]>([]);
  const [persistentTopics, setPersistentTopics] = useState<PersistentTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [minResonance, setMinResonance] = useState(2);

  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedSource, setSelectedSource] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const [itemList, srcList] = await Promise.all([
        trendingApi.list({
          category: selectedCategory || undefined,
          source: selectedSource || undefined,
          limit: 200,
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

  const fetchClusters = useCallback(async () => {
    setLoading(true);
    try {
      const data = await trendingApi.crossPlatform({ min_resonance: minResonance, limit: 50 });
      setClusters(data.clusters || []);
    } catch (e) {
      console.error('Failed to fetch cross-platform:', e);
    } finally {
      setLoading(false);
    }
  }, [minResonance]);

  const fetchPersistent = useCallback(async () => {
    setLoading(true);
    try {
      const data = await trendingApi.persistent({ min_days: 2, min_sources: 1, days_back: 7 });
      setPersistentTopics(data.topics || []);
    } catch (e) {
      console.error('Failed to fetch persistent:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'list') fetchList();
    else if (tab === 'resonance') fetchClusters();
    else fetchPersistent();
  }, [tab, fetchList, fetchClusters, fetchPersistent]);

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      await trendingApi.syncAll();
      if (tab === 'list') await fetchList();
      else await fetchClusters();
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
    <div style={{ padding: '32px 40px', maxWidth: 1400, margin: '0 auto', paddingBottom: 80, minHeight: '100%', boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: T.gray900, margin: 0 }}>
            趋势雷达
          </h1>
          <p style={{ fontSize: 13, color: T.gray400, margin: '4px 0 0' }}>
            {tab === 'list'
              ? `多平台热搜实时榜单 · ${items.length} 条`
              : `跨平台热点交叉发现 · ${clusters.length} 个共振话题`}
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

      {/* Tab Switcher */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: `2px solid ${T.gray100}` }}>
        {[
          { key: 'list' as const, label: '榜单' },
          { key: 'resonance' as const, label: '共振发现' },
          { key: 'persistent' as const, label: '持续热度' },
        ].map(t => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: '8px 20px', fontSize: 14, fontWeight: active ? 600 : 400,
                background: 'transparent', color: active ? T.primary : T.gray500,
                border: 'none',
                borderBottom: active ? `2px solid ${T.primary}` : '2px solid transparent',
                marginBottom: -2, cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {t.label}
              {t.key === 'resonance' && (
                <span style={{
                  marginLeft: 6, fontSize: 10, fontWeight: 700,
                  background: '#FEE2E2', color: '#EF4444',
                  padding: '1px 5px', borderRadius: 8,
                }}>NEW</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Resonance Filter (only on resonance tab) */}
      {tab === 'resonance' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <span style={{ fontSize: 13, color: T.gray500 }}>最低共振：</span>
          {[1, 2, 3, 4, 5].map(r => {
            const active = minResonance === r;
            return (
              <button
                key={r}
                onClick={() => setMinResonance(r)}
                style={{
                  padding: '4px 12px', fontSize: 12, fontWeight: active ? 600 : 400,
                  background: active
                    ? (RESONANCE_COLORS[r]?.bg || T.gray100)
                    : T.white,
                  color: active
                    ? (RESONANCE_COLORS[r]?.color || T.gray900)
                    : T.gray600,
                  border: `1px solid ${active ? (RESONANCE_COLORS[r]?.color || T.primary) : T.gray200}`,
                  borderRadius: 12, cursor: 'pointer',
                }}
              >
                {r}平台+
              </button>
            );
          })}
          <span style={{ fontSize: 11, color: T.gray400, marginLeft: 4 }}>
            共 {clusters.length} 个话题
          </span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          加载中...
        </div>
      )}

      {/* Resonance Tab Content */}
      {!loading && tab === 'resonance' && (
        <div>
          {clusters.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
              暂无共振数据，切换「1平台+」试试
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {clusters.map((cluster, idx) => (
                <ClusterCard key={`${cluster.topic}-${idx}`} cluster={cluster} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Persistent Hot Tab Content */}
      {!loading && tab === 'persistent' && (
        <div>
          <p style={{ fontSize: 13, color: T.gray500, margin: '0 0 16px 0' }}>
            连续多天在榜的话题 = 不是昙花一现，真正值得关注 · 跨平台共振 = 社会级话题
          </p>
          {persistentTopics.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
              暂无持续热度数据，需积累多天快照
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {persistentTopics.map((topic, idx) => {
                const brand0 = sourceBrand(topic.sources[0] || 'weibo');
                return (
                  <div key={idx} style={{
                    display: 'flex', alignItems: 'center', gap: 16,
                    padding: '14px 18px', background: T.white,
                    border: `1px solid ${T.gray100}`, borderRadius: T.radiusMd,
                  }}>
                    {/* 在榜天数 badge */}
                    <div style={{
                      minWidth: 52, height: 52, borderRadius: 12,
                      display: 'flex', flexDirection: 'column',
                      alignItems: 'center', justifyContent: 'center',
                      background: topic.days_on_list >= 3 ? '#FEE2E2' : topic.days_on_list >= 2 ? '#FEF3C7' : '#F0FDF4',
                      color: topic.days_on_list >= 3 ? '#DC2626' : topic.days_on_list >= 2 ? '#D97706' : '#16A34A',
                      fontWeight: 700, fontSize: 18, lineHeight: 1,
                    }}>
                      {topic.days_on_list}
                      <span style={{ fontSize: 9, fontWeight: 500, marginTop: 2 }}>天在榜</span>
                    </div>

                    {/* 主体 */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: T.gray800,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {topic.title}
                      </div>
                      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                        {topic.sources.map(s => {
                          const b = sourceBrand(s);
                          return (
                            <span key={s} style={{
                              fontSize: 11, color: b.color, background: b.bg,
                              padding: '2px 8px', borderRadius: 10, fontWeight: 500,
                            }}>
                              {SOURCE_LABELS[s] || s}
                            </span>
                          );
                        })}
                      </div>
                    </div>

                    {/* 右侧指标 */}
                    <div style={{ display: 'flex', gap: 20, flexShrink: 0 }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 18, fontWeight: 700, color: T.gray700 }}>
                          {topic.source_count}
                        </div>
                        <div style={{ fontSize: 10, color: T.gray400 }}>平台</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 18, fontWeight: 700, color: T.gray700 }}>
                          #{topic.best_rank || '-'}
                        </div>
                        <div style={{ fontSize: 10, color: T.gray400 }}>最佳排名</div>
                      </div>
                      {/* 排名趋势迷你图 */}
                      {topic.rank_trend && topic.rank_trend.length > 1 && (
                        <div style={{ width: 80, height: 36, position: 'relative' }}>
                          <svg viewBox="0 0 80 36" style={{ width: '100%', height: '100%' }}>
                            {(() => {
                              const vals = topic.rank_trend.filter(v => v > 0);
                              if (vals.length < 2) return null;
                              const maxR = Math.max(...vals);
                              const minR = Math.min(...vals);
                              const range = maxR - minR || 1;
                              const pts = vals.map((v, i) => {
                                const x = (i / (vals.length - 1)) * 76 + 2;
                                const y = 34 - ((v - minR) / range) * 30;
                                return `${x},${y}`;
                              });
                              return (
                                <polyline
                                  points={pts.join(' ')}
                                  fill="none" stroke={brand0.color}
                                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                                />
                              );
                            })()}
                          </svg>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Category Filter (only on list tab) */}
      {!loading && tab === 'list' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
          {CATEGORIES.map(c => {
            const active = selectedCategory === c.value;
            const catColor = c.value ? (CATEGORY_COLORS[c.value] || { bg: T.gray100, color: T.gray600 }) : { bg: T.primaryLight, color: T.primary };
            return (
              <button
                key={c.value}
                onClick={() => setSelectedCategory(c.value)}
                style={{
                  padding: '4px 14px', fontSize: 12, fontWeight: active ? 600 : 400,
                  background: active ? (catColor.bg) : T.white,
                  color: active ? (catColor.color) : T.gray600,
                  border: `1px solid ${active ? (catColor.color) : T.gray200}`,
                  borderRadius: 14, cursor: 'pointer',
                  transition: 'all 0.12s ease',
                }}
              >
                {c.label}
              </button>
            );
          })}
          <span style={{ fontSize: 11, color: T.gray400, marginLeft: 4 }}>
            {Object.keys(groupedItems).length} 个信源 · {items.length} 条
          </span>
        </div>
      )}

      {/* List Tab Content: NewsNow-style card grid */}
      {!loading && tab === 'list' && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
          gap: 16,
          alignContent: 'start',
        }}>
          {Object.entries(groupedItems).map(([source, srcItems]) => {
            const brand = sourceBrand(source);
            const sourceInfo = sources.find(s => s.source === source);
            const lastSynced = sourceInfo?.last_synced;
            return (
              <div key={source} style={{
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radius,
                overflow: 'hidden',
                background: T.white,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
              }}
                onMouseEnter={e => {
                  const el = e.currentTarget as HTMLDivElement;
                  el.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                  el.style.borderColor = T.gray300;
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLDivElement;
                  el.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)';
                  el.style.borderColor = T.gray200;
                }}
              >
                {/* Card Header: source name + time badge + collapse button */}
                <div style={{
                  padding: '10px 14px',
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: brand.bg,
                  borderBottom: `1px solid ${T.gray200}`,
                  cursor: 'default',
                }}
                >
                  {/* Source icon dot */}
                  <div style={{
                    width: 28, height: 28, borderRadius: 8,
                    background: brand.color,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: T.white }}>
                      {(SOURCE_LABELS[source] || source).charAt(0)}
                    </span>
                  </div>
                  {/* Source name */}
                  <span style={{ fontSize: 13, fontWeight: 700, color: brand.color, flex: 1 }}>
                    {SOURCE_LABELS[source] || source}
                  </span>
                  {/* Category tag */}
                  <span style={{
                    fontSize: 9, fontWeight: 600,
                    background: T.white, color: brand.color,
                    padding: '2px 6px', borderRadius: 6,
                    textTransform: 'uppercase', letterSpacing: '0.04em',
                  }}>
                  </span>
                  {/* Count badge */}
                  <span style={{
                    fontSize: 9, color: brand.color,
                    background: T.white, padding: '2px 6px', borderRadius: 6,
                    fontWeight: 600,
                  }}>
                    {srcItems.length}条
                  </span>
                  {/* Refresh button */}
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      const btn = e.currentTarget as HTMLButtonElement;
                      btn.disabled = true;
                      btn.textContent = '...';
                      try {
                        const res = await fetch(`/api/v1/trending/sync/${source}`, { method: 'POST' });
                        const data = await res.json();
                        if (data.fetched > 0) {
                          fetchList();
                        }
                      } finally {
                        btn.disabled = false;
                        btn.textContent = '↻';
                      }
                    }}
                    style={{
                      fontSize: 12, color: brand.color, background: T.white,
                      border: `1px solid ${T.gray200}`, borderRadius: 6,
                      cursor: 'pointer', padding: '1px 6px', lineHeight: '18px',
                      fontWeight: 700,
                    }}
                    title="刷新此榜单"
                  >↻</button>
                  {/* Last synced time */}
                  {lastSynced && (
                    <span style={{
                      fontSize: 9, color: T.gray400,
                      background: T.white, padding: '1px 5px', borderRadius: 4,
                    }}>
                      {formatTime(lastSynced)}
                    </span>
                  )}
                </div>

                {/* Ranked list */}
                <div className="trending-scroll" style={{
                  maxHeight: 460,
                  overflowY: 'auto',
                  scrollbarWidth: 'thin',
                  scrollbarColor: `${T.gray300} transparent`,
                }}>
                  {srcItems.map((item, idx) => (
                    <a
                      key={item.id}
                      href={item.url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '7px 14px',
                        textDecoration: 'none',
                        background: idx < 3 ? T.gray50 : T.white,
                        borderBottom: `1px solid ${T.gray100}`,
                        transition: 'background 0.1s ease',
                      }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLAnchorElement).style.background = T.primaryLight;
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLAnchorElement).style.background = idx < 3 ? T.gray50 : T.white;
                      }}
                    >
                      {/* Rank number with color */}
                      <span style={{
                        width: 22, height: 22, borderRadius: 6,
                        background: idx === 0
                          ? 'linear-gradient(135deg, #FF6B35, #FF8F65)'
                          : idx === 1
                            ? 'linear-gradient(135deg, #FFA94D, #FFB870)'
                            : idx === 2
                              ? 'linear-gradient(135deg, #FFD59E, #FFE0B2)'
                              : T.gray100,
                        color: idx < 3 ? T.white : T.gray500,
                        fontSize: 11, fontWeight: 700,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                        fontFamily: T.mono,
                      }}>
                        {idx + 1}
                      </span>
                      {/* Title */}
                      <span style={{
                        flex: 1, fontSize: 12.5, color: T.gray800,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        lineHeight: '1.4',
                      }}>
                        {item.title}
                      </span>
                      {/* Hot value */}
                      {item.hot_value > 0 && (
                        <span style={{
                          fontSize: 10, fontFamily: T.mono, fontWeight: 500,
                          color: item.hot_value > 10000 ? T.primary : T.gray400,
                          flexShrink: 0, whiteSpace: 'nowrap',
                        }}>
                          {item.hot_value >= 10000 ? `${(item.hot_value / 10000).toFixed(1)}万` : item.hot_value.toLocaleString()}
                        </span>
                      )}
                      {/* Trend badge */}
                      <TrendBadge trend={item.trend} />
                    </a>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty */}
      {!loading && tab === 'list' && items.length === 0 && (
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
