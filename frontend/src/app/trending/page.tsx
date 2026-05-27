'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BarChart3,
  Clock3,
  ExternalLink,
  Filter,
  Gauge,
  Layers3,
  Lightbulb,
  Radar,
  RefreshCw,
  Rss,
  Star,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
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
    .trending-page {
      padding: 28px 36px 80px;
      max-width: 1480px;
      margin: 0 auto;
      min-height: 100%;
      box-sizing: border-box;
    }
    .trending-hero {
      position: relative;
      overflow: hidden;
      background: ${T.white};
      border: 1px solid ${T.gray200};
      border-radius: ${T.radius}px;
      padding: 22px 24px;
      box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
    }
    .trending-hero::before {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 0;
      height: 4px;
      background: linear-gradient(90deg, ${T.primary}, ${T.teal});
    }
    .trending-hero-grid {
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: start;
    }
    .trending-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 18px;
    }
    .trending-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 300px;
      gap: 18px;
      align-items: start;
      margin-top: 18px;
    }
    .trending-main {
      min-width: 0;
    }
    .trending-sidebar {
      position: sticky;
      top: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
    }
    .trending-source-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 14px;
      align-content: start;
    }
    @media (max-width: 1120px) {
      .trending-layout { grid-template-columns: 1fr; }
      .trending-sidebar { position: static; grid-row: 1; }
    }
    @media (max-width: 760px) {
      .trending-page { padding: 18px 14px 64px; }
      .trending-hero { padding: 18px; }
      .trending-hero-grid { grid-template-columns: 1fr; }
      .trending-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .trending-source-grid { grid-template-columns: 1fr; }
    }
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

const TREND_ICONS: Record<string, LucideIcon> = {
  up: ArrowUp, down: ArrowDown, new: Star, stable: ArrowRight,
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
  const Icon = TREND_ICONS[trend] || ArrowRight;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontSize: 10, fontWeight: 700, padding: '1px 5px',
      borderRadius: 4, background: c.bg, color: c.color,
    }}>
      <Icon size={11} strokeWidth={2.2} fill={trend === 'new' ? c.color : 'none'} />
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

function Surface({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section style={{
      background: T.white,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      padding: 16,
      ...style,
    }}>
      {children}
    </section>
  );
}

function PanelTitle({
  icon: Icon,
  title,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <Icon size={15} color={T.primary} strokeWidth={2.2} />
        <span style={{ fontSize: 13, fontWeight: 800, color: T.gray900 }}>{title}</span>
      </div>
      {hint && <span style={{ fontSize: 11, color: T.gray400, whiteSpace: 'nowrap' }}>{hint}</span>}
    </div>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  hint,
  color,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint: string;
  color: string;
}) {
  return (
    <div style={{
      background: T.gray50,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radiusSm,
      padding: '13px 14px',
      minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}>
        <Icon size={14} color={color} strokeWidth={2.2} />
        <span style={{ fontSize: 11, fontWeight: 800, color: T.gray500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 25, lineHeight: 1, fontWeight: 900, color: T.gray900, fontFamily: T.mono }}>
        {value}
      </div>
      <div style={{ marginTop: 5, fontSize: 10.5, color: T.gray400 }}>{hint}</div>
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Surface style={{ textAlign: 'center', padding: 72, color: T.gray400, fontSize: 14 }}>
      {children}
    </Surface>
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
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <ArrowRight size={12} strokeWidth={2} />
                  {c.angle}
                </span>
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
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            查看详情
            <ExternalLink size={12} strokeWidth={2} />
          </span>
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
      background: T.white,
      boxShadow: '0 10px 26px rgba(15, 23, 42, 0.04)',
      transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
    }}>
      {/* 卡片头部 */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: '14px 16px',
          cursor: 'pointer',
          background: expanded ? '#FFFBF8' : T.white,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          {/* 左侧：共振强度标识 */}
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: RESONANCE_COLORS[cluster.resonance]?.bg || T.gray100,
            color: RESONANCE_COLORS[cluster.resonance]?.color || T.gray500,
            border: `1px solid ${T.gray100}`,
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
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                {expanded ? '收起' : '展开'}
                {expanded ? <ArrowUp size={12} strokeWidth={2} /> : <ArrowDown size={12} strokeWidth={2} />}
              </span>
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
              background: T.tealLight, color: T.teal,
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
          background: '#FFFBF8',
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

  const activeLabel = tab === 'list' ? '榜单扫描' : tab === 'resonance' ? '共振发现' : '持续热度';
  const topSources = Object.entries(groupedItems)
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 8);

  return (
    <div className="trending-page">
      <section className="trending-hero">
        <div className="trending-hero-grid">
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', marginBottom: 12 }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 11,
                fontWeight: 900,
                color: T.primary,
                background: T.primaryLight,
                border: `1px solid ${T.primaryBorder}`,
                borderRadius: 999,
                padding: '4px 10px',
                fontFamily: T.mono,
              }}>
                <Radar size={13} strokeWidth={2.4} />
                TREND RADAR
              </span>
              <span style={{ fontSize: 12, fontWeight: 700, color: T.gray500 }}>{activeLabel}</span>
            </div>
            <h1 style={{ fontSize: 28, lineHeight: 1.12, fontWeight: 900, color: T.gray900, margin: 0 }}>
              趋势雷达工作台
            </h1>
            <p style={{ fontSize: 13, lineHeight: 1.7, color: T.gray500, margin: '8px 0 0', maxWidth: 760 }}>
              把多平台榜单、跨平台共振和持续热度放在同一个扫描台里，优先看到正在扩散、已经共振、还在持续的内容信号。
            </p>
          </div>
          <button
            onClick={handleSyncAll}
            disabled={syncing}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 7,
              padding: '9px 17px',
              fontSize: 13,
              fontWeight: 800,
              background: syncing ? T.gray200 : T.primary,
              color: T.white,
              border: 'none',
              borderRadius: T.radiusSm,
              cursor: syncing ? 'wait' : 'pointer',
              transition: 'all 0.15s ease',
              whiteSpace: 'nowrap',
              boxShadow: syncing ? 'none' : '0 10px 22px rgba(255, 107, 53, 0.18)',
            }}
          >
            <RefreshCw size={14} strokeWidth={2.3} />
            {syncing ? '同步中...' : '刷新全量'}
          </button>
        </div>
        <div className="trending-stats">
          <StatTile icon={Rss} label="信源" value={filteredSources.length || sources.length} hint="当前可扫描平台" color={T.primary} />
          <StatTile icon={Layers3} label="样本" value={items.length} hint="榜单候选内容" color={T.teal} />
          <StatTile icon={Activity} label="共振" value={clusters.length} hint={`最低 ${minResonance} 平台`} color={T.red} />
          <StatTile icon={Clock3} label="持续" value={persistentTopics.length} hint="近 7 天持续话题" color={T.amber} />
        </div>
      </section>

      <div className="trending-layout">
        <main className="trending-main">
          {loading && <EmptyState>加载中...</EmptyState>}

          {!loading && tab === 'resonance' && (
            clusters.length === 0 ? (
              <EmptyState>暂无共振数据，切换「1平台+」试试</EmptyState>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {clusters.map((cluster, idx) => (
                  <ClusterCard key={`${cluster.topic}-${idx}`} cluster={cluster} />
                ))}
              </div>
            )
          )}

          {!loading && tab === 'persistent' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <Surface style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px', background: T.tealLight, borderColor: T.tealBorder }}>
                <Gauge size={16} color={T.teal} strokeWidth={2.3} />
                <span style={{ fontSize: 13, color: T.gray700, fontWeight: 700 }}>
                  连续多天在榜的话题代表热度韧性，适合沉淀成复盘、观察和解释型选题。
                </span>
              </Surface>
              {persistentTopics.length === 0 ? (
                <EmptyState>暂无持续热度数据，需积累多天快照</EmptyState>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {persistentTopics.map((topic, idx) => {
                    const brand0 = sourceBrand(topic.sources[0] || 'weibo');
                    return (
                      <div key={idx} style={{
                        display: 'grid',
                        gridTemplateColumns: '64px minmax(0, 1fr) auto',
                        alignItems: 'center',
                        gap: 16,
                        padding: '15px 18px',
                        background: T.white,
                        border: `1px solid ${T.gray200}`,
                        borderRadius: T.radius,
                        boxShadow: '0 8px 22px rgba(15, 23, 42, 0.035)',
                      }}>
                        <div style={{
                          minWidth: 58,
                          height: 58,
                          borderRadius: 14,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: topic.days_on_list >= 3 ? T.primaryLight : topic.days_on_list >= 2 ? T.amberLight : T.tealLight,
                          color: topic.days_on_list >= 3 ? T.primary : topic.days_on_list >= 2 ? T.amber : T.teal,
                          border: `1px solid ${topic.days_on_list >= 3 ? T.primaryBorder : topic.days_on_list >= 2 ? T.amberBorder : T.tealBorder}`,
                          fontWeight: 900,
                          fontSize: 20,
                          lineHeight: 1,
                          fontFamily: T.mono,
                        }}>
                          {topic.days_on_list}
                          <span style={{ fontSize: 9, fontWeight: 800, marginTop: 4, fontFamily: T.sans }}>天在榜</span>
                        </div>

                        <div style={{ minWidth: 0 }}>
                          <div style={{
                            fontSize: 15,
                            fontWeight: 800,
                            color: T.gray900,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}>
                            {topic.title}
                          </div>
                          <div style={{ display: 'flex', gap: 6, marginTop: 7, flexWrap: 'wrap' }}>
                            {topic.sources.map(s => {
                              const b = sourceBrand(s);
                              return (
                                <span key={s} style={{
                                  fontSize: 11,
                                  color: b.color,
                                  background: b.bg,
                                  padding: '2px 8px',
                                  borderRadius: 10,
                                  fontWeight: 700,
                                }}>
                                  {SOURCE_LABELS[s] || s}
                                </span>
                              );
                            })}
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexShrink: 0 }}>
                          <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 18, fontWeight: 900, color: T.gray800, fontFamily: T.mono }}>
                              {topic.source_count}
                            </div>
                            <div style={{ fontSize: 10, color: T.gray400 }}>平台</div>
                          </div>
                          <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 18, fontWeight: 900, color: T.gray800, fontFamily: T.mono }}>
                              #{topic.best_rank || '-'}
                            </div>
                            <div style={{ fontSize: 10, color: T.gray400 }}>最佳</div>
                          </div>
                          {topic.rank_trend && topic.rank_trend.length > 1 && (
                            <div style={{ width: 84, height: 38, position: 'relative' }}>
                              <svg viewBox="0 0 84 38" style={{ width: '100%', height: '100%' }}>
                                {(() => {
                                  const vals = topic.rank_trend.filter(v => v > 0);
                                  if (vals.length < 2) return null;
                                  const maxR = Math.max(...vals);
                                  const minR = Math.min(...vals);
                                  const range = maxR - minR || 1;
                                  const pts = vals.map((v, i) => {
                                    const x = (i / (vals.length - 1)) * 78 + 3;
                                    const y = 35 - ((v - minR) / range) * 30;
                                    return `${x},${y}`;
                                  });
                                  return (
                                    <polyline
                                      points={pts.join(' ')}
                                      fill="none"
                                      stroke={brand0.color}
                                      strokeWidth="2"
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
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

          {!loading && tab === 'list' && items.length === 0 && (
            <EmptyState>暂无趋势数据，点击右上角「刷新全量」同步</EmptyState>
          )}

          {!loading && tab === 'list' && items.length > 0 && (
            <div className="trending-source-grid">
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
                      try {
                        const res = await fetch(`/api/v1/trending/sync/${source}`, { method: 'POST' });
                        const data = await res.json();
                        if (data.fetched > 0) {
                          fetchList();
                        }
                      } finally {
                        btn.disabled = false;
                      }
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 24,
                      height: 22,
                      color: brand.color,
                      background: T.white,
                      border: `1px solid ${T.gray200}`, borderRadius: 6,
                      cursor: 'pointer',
                      padding: 0,
                    }}
                    title="刷新此榜单"
                  >
                    <RefreshCw size={12} strokeWidth={2.2} />
                  </button>
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
        </main>

        <aside className="trending-sidebar">
          <Surface>
            <PanelTitle icon={BarChart3} title="视图切换" hint={activeLabel} />
            <div style={{ display: 'grid', gap: 8 }}>
              {[
                { key: 'list' as const, label: '榜单扫描', desc: '按信源查看实时榜单' },
                { key: 'resonance' as const, label: '共振发现', desc: '同一主题跨平台出现' },
                { key: 'persistent' as const, label: '持续热度', desc: '多天仍在扩散的话题' },
              ].map(t => {
                const active = tab === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '10px 11px',
                      borderRadius: T.radiusSm,
                      border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                      background: active ? T.primaryLight : T.white,
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 800, color: active ? T.primary : T.gray800 }}>{t.label}</span>
                      {active && <span style={{ width: 7, height: 7, borderRadius: 999, background: T.primary }} />}
                    </div>
                    <div style={{ marginTop: 3, fontSize: 11, lineHeight: 1.45, color: T.gray400 }}>{t.desc}</div>
                  </button>
                );
              })}
            </div>
          </Surface>

          {tab === 'list' && (
            <Surface>
              <PanelTitle icon={Filter} title="榜单筛选" hint={`${Object.keys(groupedItems).length} 个信源`} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 13 }}>
                {CATEGORIES.map(c => {
                  const active = selectedCategory === c.value;
                  const catColor = c.value ? (CATEGORY_COLORS[c.value] || { bg: T.gray100, color: T.gray600 }) : { bg: T.primaryLight, color: T.primary };
                  return (
                    <button
                      key={c.value}
                      onClick={() => {
                        setSelectedCategory(c.value);
                        setSelectedSource('');
                      }}
                      style={{
                        padding: '5px 10px',
                        fontSize: 12,
                        fontWeight: active ? 800 : 600,
                        background: active ? catColor.bg : T.white,
                        color: active ? catColor.color : T.gray600,
                        border: `1px solid ${active ? catColor.color : T.gray200}`,
                        borderRadius: 999,
                        cursor: 'pointer',
                      }}
                    >
                      {c.label}
                    </button>
                  );
                })}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, maxHeight: 270, overflowY: 'auto' }}>
                {filteredSources.slice(0, 16).map(src => {
                  const brand = sourceBrand(src.source);
                  const active = selectedSource === src.source;
                  return (
                    <button
                      key={src.source}
                      onClick={() => setSelectedSource(active ? '' : src.source)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        width: '100%',
                        padding: '7px 8px',
                        borderRadius: T.radiusXs,
                        border: `1px solid ${active ? brand.color : T.gray100}`,
                        background: active ? brand.bg : T.gray50,
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <span style={{ width: 8, height: 8, borderRadius: 999, background: brand.color, flexShrink: 0 }} />
                      <span style={{ flex: 1, minWidth: 0, fontSize: 12, fontWeight: 700, color: T.gray700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {brand.label}
                      </span>
                      <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
                        {(groupedItems[src.source] || []).length}
                      </span>
                    </button>
                  );
                })}
              </div>
            </Surface>
          )}

          {tab === 'resonance' && (
            <Surface>
              <PanelTitle icon={Activity} title="共振阈值" hint={`${clusters.length} 个话题`} />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 7 }}>
                {[1, 2, 3, 4, 5].map(r => {
                  const active = minResonance === r;
                  return (
                    <button
                      key={r}
                      onClick={() => setMinResonance(r)}
                      style={{
                        padding: '8px 0',
                        fontSize: 12,
                        fontWeight: active ? 900 : 700,
                        background: active ? (RESONANCE_COLORS[r]?.bg || T.gray100) : T.white,
                        color: active ? (RESONANCE_COLORS[r]?.color || T.gray900) : T.gray500,
                        border: `1px solid ${active ? (RESONANCE_COLORS[r]?.color || T.primary) : T.gray200}`,
                        borderRadius: T.radiusXs,
                        cursor: 'pointer',
                        fontFamily: T.mono,
                      }}
                    >
                      {r}+
                    </button>
                  );
                })}
              </div>
              <p style={{ fontSize: 11, color: T.gray400, lineHeight: 1.6, margin: '12px 0 0' }}>
                阈值越高，越偏向社会级话题；阈值越低，更适合捕捉早期扩散苗头。
              </p>
            </Surface>
          )}

          <Surface>
            <PanelTitle icon={Rss} title="信源构成" hint={`${items.length} 条`} />
            {topSources.length === 0 ? (
              <div style={{ fontSize: 12, color: T.gray400 }}>暂无样本</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {topSources.map(([source, srcItems]) => {
                  const brand = sourceBrand(source);
                  const width = Math.max(8, Math.round((srcItems.length / Math.max(items.length, 1)) * 100));
                  return (
                    <div key={source}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 5 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: T.gray700 }}>{brand.label}</span>
                        <span style={{ fontSize: 11, color: T.gray400, fontFamily: T.mono }}>{srcItems.length}</span>
                      </div>
                      <div style={{ height: 6, borderRadius: 999, background: T.gray100, overflow: 'hidden' }}>
                        <div style={{ width: `${width}%`, height: '100%', borderRadius: 999, background: brand.color }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Surface>
        </aside>
      </div>
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
