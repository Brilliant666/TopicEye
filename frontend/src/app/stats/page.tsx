'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  BarChart3,
  BookOpen,
  CalendarDays,
  Database,
  Gauge,
  Layers3,
  PieChart,
  RadioTower,
  RefreshCw,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import {
  statsApi,
  type StatsOverview,
  type StatsSourceItem,
  type StatsCategoryItem,
  type StatsTrendItem,
  type StatsNovelPlatform,
} from '@/lib/api';

// ── Color helpers ──────────────────────────────────────────────
const BAR_COLORS = [T.primary, T.teal, T.amber, '#2563EB', '#E11D48', '#059669', '#D97706', '#64748B'];
const SOURCE_TYPE_COLOR: Record<string, string> = {
  rss: T.teal,
  rsshub: '#059669',
  hackernews: T.purple,
  api: T.primary,
  reddit: T.amber,
  zhihu: '#2563EB',
  公众号: '#E11D48',
  小红书: '#EC4899',
  unknown: T.gray400,
};

function barColor(idx: number) {
  return BAR_COLORS[idx % BAR_COLORS.length];
}

// ── Reusable chart components ──────────────────────────────────

function MiniBar({ value, max, color, height = 8 }: { value: number; max: number; color: string; height?: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{ width: '100%', height, background: T.gray200, borderRadius: height / 2, overflow: 'hidden' }}>
      <div
        style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: height / 2,
          transition: 'width 0.4s ease',
        }}
      />
    </div>
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
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <Icon size={16} color={T.primary} strokeWidth={2.2} />
        <span style={{ fontSize: 14, fontWeight: 850, color: T.gray900 }}>{title}</span>
      </div>
      {hint && <span style={{ fontSize: 11, color: T.gray400, whiteSpace: 'nowrap' }}>{hint}</span>}
    </div>
  );
}

function Surface({
  title,
  icon,
  hint,
  children,
  style,
}: {
  title: string;
  icon: LucideIcon;
  hint?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section style={{
      background: T.white,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      padding: '18px 20px',
      ...style,
    }}>
      <PanelTitle icon={icon} title={title} hint={hint} />
      {children}
    </section>
  );
}

function HorizontalBarChart({
  items,
  valueKey,
  labelKey,
  extraKey,
}: {
  items: Array<Record<string, unknown>>;
  valueKey: string;
  labelKey: string;
  extraKey?: string;
}) {
  if (!items || items.length === 0)
    return <div style={{ color: T.gray400, fontSize: 13, padding: '12px 0' }}>暂无数据</div>;

  const maxVal = Math.max(...items.map(it => (it[valueKey] as number) || 0), 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((it, i) => {
        const val = (it[valueKey] as number) || 0;
        const label = (it[labelKey] as string) || '-';
        const extra = extraKey ? (it[extraKey] as string | number | null) : null;
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 80,
                fontSize: 13,
                color: T.gray700,
                fontWeight: 500,
                textAlign: 'right',
                flexShrink: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <MiniBar value={val} max={maxVal} color={barColor(i)} height={14} />
            </div>
            <div style={{ width: 56, fontSize: 12, fontFamily: T.mono, color: T.gray600, textAlign: 'right' }}>
              {val}
              {extra !== null && extra !== undefined && (
                <span style={{ color: T.gray400, marginLeft: 4, fontSize: 10 }}>{extra}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function formatDayKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatShortDate(dateKey: string) {
  const date = new Date(`${dateKey}T00:00:00`);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function getHeatColor(value: number, max: number) {
  if (value <= 0) return T.gray100;
  const ratio = value / Math.max(max, 1);
  if (ratio >= 0.82) return T.teal;
  if (ratio >= 0.56) return T.primary;
  if (ratio >= 0.28) return T.primaryBorder;
  return T.primaryLight;
}

function ContributionHeatmap({ data, days }: { data: StatsTrendItem[]; days: number }) {
  const byDate = new Map(data.map(day => [day.date, day]));
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sortedDates = data
    .map(day => new Date(`${day.date}T00:00:00`))
    .filter(date => !Number.isNaN(date.getTime()))
    .sort((a, b) => a.getTime() - b.getTime());
  const start = sortedDates[0] ? new Date(sortedDates[0]) : new Date(today);
  if (!sortedDates[0]) {
    start.setDate(today.getDate() - Math.max(days - 1, 0));
  }
  const end = sortedDates[sortedDates.length - 1] ? new Date(sortedDates[sortedDates.length - 1]) : new Date(today);
  if (end.getTime() < today.getTime()) {
    end.setTime(today.getTime());
  }

  const cells: Array<{ date: string; item: StatsTrendItem | null; empty?: boolean }> = [];
  const startWeekday = start.getDay();
  for (let i = 0; i < startWeekday; i += 1) {
    cells.push({ date: `empty-${i}`, item: null, empty: true });
  }
  const spanDays = Math.max(1, Math.floor((end.getTime() - start.getTime()) / 86400000) + 1);
  for (let i = 0; i < spanDays; i += 1) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    const dateKey = formatDayKey(date);
    cells.push({ date: dateKey, item: byDate.get(dateKey) ?? null });
  }

  const total = data.reduce((sum, day) => sum + day.content_count, 0);
  const curated = data.reduce((sum, day) => sum + day.curated_count, 0);
  const maxCount = Math.max(...data.map(day => day.content_count), 1);
  const peak = data.reduce<StatsTrendItem | null>(
    (current, day) => (!current || day.content_count > current.content_count ? day : current),
    null,
  );

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(118px, 1fr))', gap: 10, marginBottom: 14 }}>
        {[
          { label: '入库总量', value: total, color: T.primary },
          { label: '精选内容', value: curated, color: T.teal },
          { label: '峰值日期', value: peak ? peak.content_count : 0, color: T.gray700, sub: peak ? formatShortDate(peak.date) : '-' },
        ].map(item => (
          <div
            key={item.label}
            style={{
              border: `1px solid ${T.gray200}`,
              borderRadius: T.radiusSm,
              background: T.gray50,
              padding: '10px 12px',
              minWidth: 0,
            }}
          >
            <div style={{ fontSize: 11, fontWeight: 800, color: T.gray500, marginBottom: 4 }}>{item.label}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, minWidth: 0 }}>
              <span style={{ fontSize: 22, lineHeight: 1, fontWeight: 900, fontFamily: T.mono, color: item.color }}>
                {item.value}
              </span>
              <span style={{ fontSize: 11, color: T.gray400 }}>{item.sub ?? '条'}</span>
            </div>
          </div>
        ))}
      </div>

      {cells.length > 0 ? (
        <div style={{ overflowX: 'auto', paddingBottom: 2 }}>
          <div
            style={{
              display: 'grid',
              gridTemplateRows: 'repeat(7, 14px)',
              gridAutoFlow: 'column',
              gridAutoColumns: 14,
              gap: 4,
              width: 'max-content',
              minWidth: '100%',
            }}
          >
            {cells.map(cell => {
              const count = cell.item?.content_count ?? 0;
              const curatedCount = cell.item?.curated_count ?? 0;
              const analyzedCount = cell.item?.analyzed_count ?? 0;
              return (
                <div
                  key={cell.date}
                  title={
                    cell.empty
                      ? ''
                      : `${cell.date}: 入库 ${count} 条，精选 ${curatedCount} 条，已分析 ${analyzedCount} 条`
                  }
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 3,
                    background: cell.empty ? 'transparent' : getHeatColor(count, maxCount),
                    border: cell.empty ? '1px solid transparent' : `1px solid ${count > 0 ? 'rgba(255,107,53,0.16)' : T.gray200}`,
                  }}
                />
              );
            })}
          </div>
        </div>
      ) : (
        <div style={{ color: T.gray400, fontSize: 13, padding: '12px 0' }}>暂无趋势数据</div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 14, fontSize: 11, color: T.gray500, flexWrap: 'wrap' }}>
          <span>起始 {formatShortDate(formatDayKey(start))}</span>
          <span>结束 {formatShortDate(formatDayKey(today))}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: T.gray400 }}>
          <span>少</span>
          {[0, 1, 3, 6, 9].map(level => (
            <span
              key={level}
              style={{
                width: 12,
                height: 12,
                borderRadius: 3,
                border: `1px solid ${level === 0 ? T.gray200 : 'rgba(255,107,53,0.16)'}`,
                background: getHeatColor(level, 9),
              }}
            />
          ))}
          <span>多</span>
        </div>
      </div>
    </div>
  );
}

function formatSyncLabel(lastSync: string | null) {
  if (!lastSync) return '未同步';
  try {
    const dt = new Date(lastSync);
    const now = new Date();
    const diffMs = now.getTime() - dt.getTime();
    const diffMin = Math.max(0, Math.floor(diffMs / 60000));
    if (diffMin < 60) return `${diffMin}分钟前`;
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}小时前`;
    return `${Math.floor(diffMin / 1440)}天前`;
  } catch {
    return lastSync;
  }
}

function NovelPlatformStats({ platforms }: { platforms: StatsNovelPlatform[] }) {
  if (platforms.length === 0) {
    return <div style={{ color: T.gray400, fontSize: 13 }}>暂无数据</div>;
  }

  const platformColors = [
    { bg: '#FFF4EE', color: T.primary, border: T.primaryBorder },
    { bg: '#E6FAF5', color: T.teal, border: T.tealBorder },
    { bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
      {platforms.map((platform, i) => {
        const pc = platformColors[i % platformColors.length];
        return (
          <div
            key={platform.table}
            style={{
              background: pc.bg,
              border: `1px solid ${pc.border}`,
              borderRadius: T.radiusSm,
              padding: '14px 16px',
              display: 'flex',
              flexDirection: 'column',
              minWidth: 0,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 850, color: pc.color, marginBottom: 8 }}>
              {platform.name}
            </div>
            <div style={{ fontSize: 30, fontWeight: 900, color: pc.color, fontFamily: T.mono, lineHeight: 1 }}>
              {platform.count}
              <span style={{ fontSize: 12, fontWeight: 500, marginLeft: 3, color: T.gray400 }}>条</span>
            </div>
            <div style={{ fontSize: 11, color: T.gray500, marginTop: 10, display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
              <span
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: platform.last_sync ? T.teal : T.gray300,
                  flexShrink: 0,
                }}
              />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                最近同步: {formatSyncLabel(platform.last_sync)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  unit,
  color,
  sub,
  tone = 'neutral',
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  unit: string;
  color: string;
  sub: string;
  tone?: 'primary' | 'teal' | 'amber' | 'neutral';
}) {
  const toneStyle = {
    primary: { bg: T.primaryLight, border: T.primaryBorder },
    teal: { bg: T.tealLight, border: T.tealBorder },
    amber: { bg: T.amberLight, border: T.amberBorder },
    neutral: { bg: T.white, border: T.gray200 },
  }[tone];

  return (
    <div
      style={{
        background: toneStyle.bg,
        border: `1px solid ${toneStyle.border}`,
        borderRadius: T.radius,
        padding: '16px 18px',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Icon size={15} color={color} strokeWidth={2.2} />
        <span style={{ fontSize: 12, color: T.gray500, fontWeight: 800 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color, fontFamily: T.mono, lineHeight: 1.05 }}>
        {value}
        <span style={{ fontSize: 13, fontWeight: 500, marginLeft: 4, color: T.gray400 }}>{unit}</span>
      </div>
      <div style={{ fontSize: 11, color: T.gray400, marginTop: 6 }}>{sub}</div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────

export default function StatsPage() {
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State for each section
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [sources, setSources] = useState<StatsSourceItem[]>([]);
  const [categories, setCategories] = useState<StatsCategoryItem[]>([]);
  const [trend, setTrend] = useState<StatsTrendItem[]>([]);
  const [novelPlatforms, setNovelPlatforms] = useState<StatsNovelPlatform[]>([]);

  const fetchAll = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [ov, src, cat, tr, np] = await Promise.all([
        statsApi.getOverview(days),
        statsApi.getSourceDistribution(days),
        statsApi.getCategoryDistribution(days),
        statsApi.getDailyTrend(days),
        statsApi.getNovelPlatforms(),
      ]);
      setOverview(ov);
      setSources(src.sources || []);
      setCategories(cat.categories || []);
      setTrend(tr.trend || []);
      setNovelPlatforms(np.platforms || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const curatedRate = overview && overview.total > 0 ? Math.round((overview.curated / overview.total) * 100) : 0;

  // ── Donut chart approximation via CSS ──
  function SourcePieChart() {
    if (sources.length === 0)
      return <div style={{ color: T.gray400, fontSize: 13 }}>暂无数据</div>;

    const total = sources.reduce((s, it) => s + it.content_count, 0) || 1;
    // Build a horizontal stacked bar as a "pie" approximation
    return (
      <div>
        <div style={{ display: 'flex', height: 18, borderRadius: 4, overflow: 'hidden', marginBottom: 14 }}>
          {sources.map((src, i) => {
            const pct = (src.content_count / total) * 100;
            if (pct < 0.5) return null;
            return (
              <div
                key={i}
                style={{
                  width: `${pct}%`,
                  background: barColor(i),
                  transition: 'width 0.3s',
                }}
                title={`${src.source_name}: ${src.content_count} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {sources.slice(0, 10).map((src, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: barColor(i),
                  flexShrink: 0,
                }}
              />
              <span style={{ color: T.gray600, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{src.source_name}</span>
              <span style={{ fontFamily: T.mono, color: T.gray400, fontSize: 11 }}>{src.content_count}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.bg }}>
      <div style={{ padding: '28px 40px 64px', maxWidth: 1480, margin: '0 auto' }}>
        <section style={{
          position: 'relative',
          overflow: 'hidden',
          background: T.white,
          border: `1px solid ${T.gray200}`,
          borderRadius: T.radius,
          padding: '22px 24px',
          marginBottom: 18,
          boxShadow: '0 14px 36px rgba(15, 23, 42, 0.06)',
        }}>
          <div style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 0,
            height: 4,
            background: `linear-gradient(90deg, ${T.primary}, ${T.teal})`,
          }} />
          <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 20, alignItems: 'start' }}>
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
                  <BarChart3 size={13} strokeWidth={2.4} />
                  DATA DESK
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: T.gray500 }}>最近 {days} 天</span>
              </div>
              <h1 style={{ fontSize: 28, lineHeight: 1.12, fontWeight: 900, color: T.gray900, margin: 0 }}>
                数据统计工作台
              </h1>
              <p style={{ fontSize: 13, lineHeight: 1.7, color: T.gray500, margin: '8px 0 0', maxWidth: 760 }}>
                观察内容入库、精选效率、信源结构和分类覆盖，判断当前选题池是否健康、是否需要调整信源和筛选策略。
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {[7, 14, 30].map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  style={{
                    padding: '7px 12px',
                    borderRadius: T.radiusSm,
                    border: `1px solid ${days === d ? T.primary : T.gray200}`,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontWeight: 800,
                    background: days === d ? T.primaryLight : T.white,
                    color: days === d ? T.primary : T.gray600,
                    transition: 'all 0.15s',
                  }}
                >
                  {d} 天
                </button>
              ))}
              <button
                onClick={fetchAll}
                title="刷新"
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: T.radiusSm,
                  border: `1px solid ${T.gray200}`,
                  cursor: 'pointer',
                  background: T.white,
                  color: T.gray600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <RefreshCw size={15} />
              </button>
            </div>
          </div>
        </section>

        {loading && (
          <div style={{ textAlign: 'center', padding: 40, color: T.gray400 }}>加载中...</div>
        )}

        {error && (
          <div style={{ padding: 16, background: T.redLight, borderRadius: 8, color: T.red, fontSize: 13, marginBottom: 20 }}>
            {error}
          </div>
        )}

        {!loading && (
          <>
            {/* ═══════════════════════════════════════════════════
                A. 入库趋势 + 网文雷达
                ═══════════════════════════════════════════════════ */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))',
                gap: 14,
                marginBottom: 14,
                alignItems: 'start',
              }}
            >
              <Surface title="每日入库趋势" icon={CalendarDays} hint={`最近 ${days} 天`}>
                <ContributionHeatmap data={trend} days={days} />
              </Surface>

              <Surface title="网文雷达统计" icon={BookOpen}>
                <NovelPlatformStats platforms={novelPlatforms} />
              </Surface>
            </div>

            {/* ═══════════════════════════════════════════════════
                B. 内容总览 KPI Cards
                ═══════════════════════════════════════════════════ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 16 }}>
              {[
                {
                  icon: Database,
                  label: '总内容数',
                  value: overview?.total ?? 0,
                  unit: '条',
                  color: T.gray700,
                  sub: `已分析 ${overview?.analyzed ?? 0}`,
                  tone: 'neutral' as const,
                },
                {
                  icon: Gauge,
                  label: '精选内容',
                  value: overview?.curated ?? 0,
                  unit: '条',
                  color: T.primary,
                  sub: `精选率 ${curatedRate}%`,
                  tone: 'primary' as const,
                },
                {
                  icon: Activity,
                  label: '今日新增',
                  value: overview?.today_new ?? 0,
                  unit: '条',
                  color: T.teal,
                  sub: '今日 0:00 起',
                  tone: 'teal' as const,
                },
                {
                  icon: PieChart,
                  label: '精选率',
                  value: curatedRate,
                  unit: '%',
                  color: T.amber,
                  sub: `${overview?.curated ?? 0} / ${overview?.total ?? 0}`,
                  tone: 'amber' as const,
                },
              ].map(card => <KpiCard key={card.label} {...card} />)}
            </div>

            {/* ═══════════════════════════════════════════════════
                C. 信源分布 + D. 分类分布 (side by side)
                ═══════════════════════════════════════════════════ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 14, marginBottom: 14, alignItems: 'start' }}>
              {/* B. 信源分布 */}
              <Surface title="信源分布" icon={RadioTower} hint={`${sources.length} 个信源`}>
                <SourcePieChart />

                {/* Source table */}
                {sources.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ borderBottom: `1px solid ${T.gray200}` }}>
                          {['信源', '类型', '数量', '精选', '精选率'].map(h => (
                            <th
                              key={h}
                              style={{
                                textAlign: 'left',
                                padding: '4px 6px',
                                color: T.gray400,
                                fontWeight: 400,
                                fontSize: 11,
                              }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sources.slice(0, 8).map((src, i) => {
                          const color = SOURCE_TYPE_COLOR[src.source_type.toLowerCase()] || T.gray400;
                          return (
                            <tr key={i} style={{ borderBottom: `1px solid ${T.gray100}` }}>
                              <td style={{ padding: '6px', fontWeight: 500, color: T.gray800, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {src.source_name}
                              </td>
                              <td style={{ padding: '6px' }}>
                                <span
                                  style={{
                                    display: 'inline-block',
                                    padding: '1px 6px',
                                    borderRadius: 8,
                                    fontSize: 10,
                                    background: color + '20',
                                    color: color,
                                  }}
                                >
                                  {src.source_type.toUpperCase()}
                                </span>
                              </td>
                              <td style={{ padding: '6px', fontFamily: T.mono, color: T.gray600 }}>
                                {src.content_count}
                              </td>
                              <td style={{ padding: '6px', fontFamily: T.mono, color: T.primary }}>
                                {src.curated_count}
                              </td>
                              <td style={{ padding: '6px', fontFamily: T.mono, color: T.teal, fontSize: 11 }}>
                                {src.curation_rate}%
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Surface>

              {/* C. 分类分布 */}
              <Surface title="分类分布" icon={Layers3} hint={`${categories.length} 个分类`}>
                <HorizontalBarChart
                  items={categories.map(c => ({
                    category: c.category,
                    content_count: c.content_count,
                    extra: c.avg_score > 0 ? `均分${c.avg_score}` : '',
                  }))}
                  valueKey="content_count"
                  labelKey="category"
                  extraKey="extra"
                />
              </Surface>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
