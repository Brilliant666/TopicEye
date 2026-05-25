'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';
import {
  statsApi,
  type StatsOverview,
  type StatsSourceItem,
  type StatsCategoryItem,
  type StatsTrendItem,
  type StatsNovelPlatform,
} from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import Header from '@/components/Header';

// ── Color helpers ──────────────────────────────────────────────
const BAR_COLORS = [T.primary, T.teal, T.purple, T.amber, '#6366F1', '#EC4899', '#14B8A6', '#F59E0B'];
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
            <div style={{ flex: 1 }}>
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

function AreaChart({ data }: { data: StatsTrendItem[] }) {
  if (!data || data.length === 0)
    return <div style={{ color: T.gray400, fontSize: 13, padding: '12px 0' }}>暂无趋势数据</div>;

  const maxCount = Math.max(...data.map(d => d.content_count), 1);
  const barW = Math.max(20, Math.min(48, Math.floor(600 / data.length) - 8));

  return (
    <div>
      {/* Chart area */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120, marginBottom: 8 }}>
        {data.map((day, i) => {
          const totalPct = (day.content_count / maxCount) * 100;
          const curatedPct = maxCount > 0 ? (day.curated_count / maxCount) * 100 : 0;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 3,
                minWidth: barW,
              }}
            >
              {/* Tooltip numbers */}
              <div style={{ fontSize: 10, fontFamily: T.mono, color: T.gray400 }}>
                {day.content_count}
              </div>

              {/* Stacked bar: total + curated overlay */}
              <div
                style={{
                  width: '100%',
                  height: `${Math.max(totalPct, 4)}%`,
                  background: i === data.length - 1 ? T.primary + '30' : T.gray200,
                  borderRadius: '3px 3px 0 0',
                  position: 'relative',
                  minHeight: 6,
                }}
              >
                {/* curated portion (from bottom) */}
                {day.curated_count > 0 && (
                  <div
                    style={{
                      position: 'absolute',
                      bottom: 0,
                      left: 0,
                      right: 0,
                      height: `${maxCount > 0 ? (day.curated_count / day.content_count) * 100 : 0}%`,
                      background: i === data.length - 1 ? T.primary : T.teal,
                      borderRadius: '3px 3px 0 0',
                      minHeight: 3,
                    }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Date labels */}
      <div style={{ display: 'flex', gap: 6 }}>
        {data.map((day, i) => {
          const d = new Date(day.date + 'T00:00:00');
          const label = `${d.getMonth() + 1}/${d.getDate()}`;
          return (
            <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, color: T.gray400, minWidth: barW }}>
              {label}
            </div>
          );
        })}
      </div>

      {/* Analyzed row */}
      <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
        {data.map((day, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 9, color: T.teal, minWidth: barW }}>
            {day.curated_count > 0 ? `${day.curated_count}精` : '-'}
          </div>
        ))}
      </div>
    </div>
  );
}

function Card({ title, children, style }: { title: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        background: T.white,
        border: `1px solid ${T.gray200}`,
        borderRadius: 12,
        padding: 20,
        ...style,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 600, color: T.gray700, marginBottom: 16 }}>{title}</div>
      {children}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────

export default function StatsPage() {
  const { topicCount: _topicCount } = useAppContext(); // eslint-disable-line @typescript-eslint/no-unused-vars
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

  const dateStr = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });

  const curatedRate = overview && overview.total > 0 ? Math.round((overview.curated / overview.total) * 100) : 0;

  // ── Donut chart approximation via CSS ──
  function SourcePieChart() {
    if (sources.length === 0)
      return <div style={{ color: T.gray400, fontSize: 13 }}>暂无数据</div>;

    const total = sources.reduce((s, it) => s + it.content_count, 0) || 1;
    // Build a horizontal stacked bar as a "pie" approximation
    return (
      <div>
        {/* Stacked bar */}
        <div style={{ display: 'flex', height: 28, borderRadius: 14, overflow: 'hidden', marginBottom: 12 }}>
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
              <span style={{ color: T.gray600 }}>{src.source_name}</span>
              <span style={{ fontFamily: T.mono, color: T.gray400, fontSize: 11 }}>{src.content_count}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <div style={{ maxWidth: 860, margin: '0 auto', padding: '24px 20px' }}>
        <Header title="数据统计" subtitle={`统计周期：最近 ${days} 天`} date={dateStr} />

        {/* ── Time range selector ── */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {[7, 14, 30].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                padding: '4px 14px',
                borderRadius: 20,
                border: 'none',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: days === d ? 600 : 400,
                background: days === d ? T.primary : T.gray100,
                color: days === d ? T.white : T.gray600,
                transition: 'all 0.15s',
              }}
            >
              {d} 天
            </button>
          ))}
          <button
            onClick={fetchAll}
            style={{
              marginLeft: 'auto',
              padding: '4px 14px',
              borderRadius: 20,
              border: `1px solid ${T.gray200}`,
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 400,
              background: T.white,
              color: T.gray600,
              transition: 'all 0.15s',
            }}
          >
            刷新
          </button>
        </div>

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
                A. 内容总览 KPI Cards
                ═══════════════════════════════════════════════════ */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
              {[
                {
                  label: '总内容数',
                  value: overview?.total ?? 0,
                  unit: '条',
                  color: T.gray700,
                  sub: `已分析 ${overview?.analyzed ?? 0}`,
                },
                {
                  label: '精选内容',
                  value: overview?.curated ?? 0,
                  unit: '条',
                  color: T.primary,
                  sub: `精选率 ${curatedRate}%`,
                },
                {
                  label: '今日新增',
                  value: overview?.today_new ?? 0,
                  unit: '条',
                  color: T.teal,
                  sub: '今日 0:00 起',
                },
                {
                  label: '精选率',
                  value: curatedRate,
                  unit: '%',
                  color: T.purple,
                  sub: `${overview?.curated ?? 0} / ${overview?.total ?? 0}`,
                },
              ].map(card => (
                <div
                  key={card.label}
                  style={{
                    background: T.white,
                    border: `1px solid ${T.gray200}`,
                    borderRadius: 12,
                    padding: '16px 18px',
                  }}
                >
                  <div style={{ fontSize: 12, color: T.gray500, marginBottom: 6 }}>{card.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: card.color, fontFamily: T.mono, lineHeight: 1.1 }}>
                    {card.value}
                    <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 2, color: T.gray400 }}>{card.unit}</span>
                  </div>
                  <div style={{ fontSize: 11, color: T.gray400, marginTop: 4 }}>{card.sub}</div>
                </div>
              ))}
            </div>

            {/* ═══════════════════════════════════════════════════
                B. 信源分布 + C. 分类分布 (side by side)
                ═══════════════════════════════════════════════════ */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
              {/* B. 信源分布 */}
              <Card title="信源分布">
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
              </Card>

              {/* C. 分类分布 */}
              <Card title="分类分布">
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
              </Card>
            </div>

            {/* ═══════════════════════════════════════════════════
                D. 时间趋势
                ═══════════════════════════════════════════════════ */}
            <Card title="每日入库趋势" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 11, color: T.gray500 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: T.gray200 }} />
                  总内容
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: T.teal }} />
                  精选
                </span>
              </div>
              <AreaChart data={trend} />
            </Card>

            {/* ═══════════════════════════════════════════════════
                E. 网文雷达统计
                ═══════════════════════════════════════════════════ */}
            <Card title="网文雷达统计">
              {novelPlatforms.length === 0 ? (
                <div style={{ color: T.gray400, fontSize: 13 }}>暂无数据</div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                  {novelPlatforms.map((p, i) => {
                    const platformColors = [
                      { bg: '#FFF4EE', color: T.primary, border: T.primaryBorder },
                      { bg: '#E6FAF5', color: T.teal, border: T.tealBorder },
                      { bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE' },
                    ];
                    const pc = platformColors[i % platformColors.length];

                    let syncLabel = '未同步';
                    if (p.last_sync) {
                      try {
                        const dt = new Date(p.last_sync);
                        const now = new Date();
                        const diffMs = now.getTime() - dt.getTime();
                        const diffMin = Math.floor(diffMs / 60000);
                        if (diffMin < 60) {
                          syncLabel = `${diffMin}分钟前`;
                        } else if (diffMin < 1440) {
                          syncLabel = `${Math.floor(diffMin / 60)}小时前`;
                        } else {
                          syncLabel = `${Math.floor(diffMin / 1440)}天前`;
                        }
                      } catch {
                        syncLabel = p.last_sync;
                      }
                    }

                    return (
                      <div
                        key={p.table}
                        style={{
                          background: pc.bg,
                          border: `1px solid ${pc.border}`,
                          borderRadius: 12,
                          padding: '16px 18px',
                          display: 'flex',
                          flexDirection: 'column',
                        }}
                      >
                        <div style={{ fontSize: 13, fontWeight: 600, color: pc.color, marginBottom: 8 }}>
                          {p.name}
                        </div>
                        <div style={{ fontSize: 32, fontWeight: 700, color: pc.color, fontFamily: T.mono, lineHeight: 1 }}>
                          {p.count}
                          <span style={{ fontSize: 13, fontWeight: 400, marginLeft: 2, color: T.gray400 }}>条</span>
                        </div>
                        <div style={{ fontSize: 11, color: T.gray400, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span
                            style={{
                              display: 'inline-block',
                              width: 6,
                              height: 6,
                              borderRadius: '50%',
                              background: p.last_sync ? T.teal : T.gray300,
                            }}
                          />
                          最近同步: {syncLabel}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
