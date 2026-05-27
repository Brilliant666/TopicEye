'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';

/* ── Types ── */

interface TrendPoint {
  date: string;
  topic_id: number;
  topic_name: string;
  content_count: number;
  avg_score: number;
  max_score: number;
  pick_count: number;
  top_items: { title: string; url: string; score: number }[] | null;
}

interface KeywordItem {
  keyword: string;
  count: number;
}

const COLORS = [
  T.primary, T.teal, T.purple, '#3B82F6', '#F59E0B',
  '#EF4444', '#10B981', '#EC4899', '#06B6D4', '#84CC16',
];

/* ── Sparkline (SVG mini trend) ── */

function Sparkline({ data, width = 100, height = 28, color = T.primary }: {
  data: number[]; width?: number; height?: number; color?: string;
}) {
  if (data.length < 2) return <span style={{ fontSize: 11, color: T.gray300 }}>—</span>;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((v, i) => `${i * step},${height - 2 - ((v - min) / range) * (height - 6)}`).join(' ');
  const area = pts + ` ${width},${height} 0,${height}`;
  return (
    <svg width={width} height={height} style={{ display: 'inline-block', flexShrink: 0 }}>
      <polygon fill={`${color}15`} points={area} />
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

/* ── Topic trend row ── */

function TopicRow({ topic, dates, maxCount, color, isLast }: {
  topic: { name: string; pts: TrendPoint[]; total: number };
  dates: string[];
  maxCount: number;
  color: string;
  isLast: boolean;
}) {
  const counts = dates.map(d => {
    const pt = topic.pts.find(p => p.date === d);
    return pt?.content_count || 0;
  });
  const latestPt = topic.pts[topic.pts.length - 1];
  // barWidth reserved for future chart sizing
  const barH = (c: number) => c ? Math.max(4, (c / maxCount) * 32) : 0;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '12px 20px',
      borderBottom: isLast ? 'none' : `1px solid ${T.gray100}`,
      transition: 'background 0.15s',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.background = `${T.primary}04`; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
    >
      {/* Topic name */}
      <div style={{ width: 160, flexShrink: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.gray800, lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={topic.name}>
          {topic.name}
        </div>
        <div style={{ fontSize: 11, color: T.gray400, marginTop: 2 }}>
          {topic.total}条内容 · {latestPt?.pick_count || 0}精选
        </div>
      </div>

      {/* Sparkline */}
      <Sparkline data={counts} color={color} />

      {/* Bars */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, flex: 1, height: 32 }}>
        {dates.map((d, di) => {
          const h = barH(counts[di]);
          return (
            <div key={d} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
              <div
                style={{
                  width: '100%', borderRadius: '2px 2px 0 0',
                  height: h || 2,
                  background: counts[di] ? color : T.gray100,
                  opacity: counts[di] ? 0.85 : 0.4,
                  transition: 'height 0.3s ease',
                }}
                title={`${d}: ${counts[di]}条`}
              />
              {(di === 0 || di === dates.length - 1) && (
                <span style={{ fontSize: 9, color: T.gray400, marginTop: 4 }}>{d.slice(5)}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Score badge */}
      <div style={{
        fontSize: 12, fontWeight: 700, fontFamily: T.mono,
        color: latestPt?.max_score >= 80 ? T.primary : latestPt?.max_score >= 70 ? T.amber : T.gray500,
        width: 36, textAlign: 'right', flexShrink: 0,
      }}>
        {latestPt ? Math.round(latestPt.max_score) : ''}
      </div>
    </div>
  );
}

/* ── Main page ── */

export default function TrendsPage() {
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'topics' | 'keywords'>('topics');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
      const [tRes, kRes] = await Promise.all([
        fetch(`${base}/trends/topics?days=${days}`),
        fetch(`${base}/trends/keywords?days=${days}&limit=60`),
      ]);
      if (tRes.ok) { const d = await tRes.json(); setTrends(d.trends || []); }
      if (kRes.ok) { const d = await kRes.json(); setKeywords(d.keywords || []); }
    } catch (err) {
      console.error('Failed to fetch trends:', err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void fetchData(); }, [fetchData]);

  // Aggregate
  const totalTopics = new Set(trends.map(t => t.topic_id)).size;
  const totalPicks = trends.reduce((s, t) => s + t.pick_count, 0);
  const totalContent = trends.reduce((s, t) => s + t.content_count, 0);

  // Group trends by topic
  const byTopic = new Map<string, { pts: TrendPoint[]; total: number }>();
  for (const t of trends) {
    const key = `${t.topic_id}:${t.topic_name}`;
    if (!byTopic.has(key)) byTopic.set(key, { pts: [], total: 0 });
    const entry = byTopic.get(key)!;
    entry.pts.push(t);
    entry.total += t.content_count;
  }
  const sortedTopics = [...byTopic.entries()]
    .map(([key, data]) => ({ key, name: key.split(':').slice(1).join(':'), ...data }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 15);

  const dateSet = new Set(trends.map(t => t.date));
  const dates = [...dateSet].sort();
  const maxCount = Math.max(...sortedTopics.flatMap(t => t.pts.map(p => p.content_count)), 1);

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>趋势追踪</h1>
          <span style={{
            fontSize: 10, fontWeight: 700, color: T.white,
            background: `linear-gradient(135deg, ${T.teal}, #7DD3C0)`,
            padding: '3px 10px', borderRadius: 20,
          }}>
            TRENDING
          </span>
        </div>
        <p style={{ fontSize: 13, color: T.gray400 }}>
          话题热度变化 · 关键词频率 · 近 <b style={{ color: T.teal, fontFamily: T.mono }}>{days}</b> 天
        </p>
      </div>

      {/* Stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: '话题数', value: totalTopics, color: T.primary, bg: T.primaryLight },
          { label: '精选内容', value: totalPicks, color: T.amber, bg: T.amberLight },
          { label: '内容总量', value: totalContent, color: T.teal, bg: T.tealLight },
          { label: '热词数', value: keywords.length, color: T.purple, bg: T.purpleLight },
        ].map(s => (
          <div key={s.label} style={{
            background: T.white, borderRadius: T.radius, padding: '16px 20px',
            border: `1px solid ${T.gray100}`,
          }}>
            <div style={{ fontSize: 24, fontWeight: 800, fontFamily: T.mono, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 12, color: T.gray400, marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tab + Days selector */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {(['topics', 'keywords'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: T.radiusXs,
                border: 'none', cursor: 'pointer',
                background: activeTab === tab ? T.gray900 : T.white,
                color: activeTab === tab ? T.white : T.gray500,
                transition: 'all 0.15s',
              }}
            >
              {tab === 'topics' ? '📊 话题热度' : '☁️ 关键词云'}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {[3, 7, 14, 30].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                fontSize: 11, fontWeight: days === d ? 700 : 500,
                padding: '4px 10px', borderRadius: T.radiusXs,
                border: `1px solid ${days === d ? T.tealBorder : T.gray200}`,
                background: days === d ? T.tealLight : T.white,
                color: days === d ? T.teal : T.gray400,
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {d}天
            </button>
          ))}
        </div>
      </div>

      {/* Content card */}
      <div style={{
        background: T.white, borderRadius: T.radius,
        border: `1px solid ${T.gray100}`, overflow: 'hidden',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.3 }}>⏳</div>
            加载中...
          </div>
        ) : activeTab === 'topics' ? (
          /* ── Topics tab ── */
          <>
            <div style={{
              padding: '14px 20px', borderBottom: `1px solid ${T.gray100}`,
              background: `linear-gradient(135deg, ${T.teal}06, ${T.teal}02)`,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: T.gray900 }}>
                话题内容量趋势（近{days}天）
              </span>
              <span style={{
                marginLeft: 'auto', fontSize: 11, fontWeight: 600,
                color: T.teal, background: T.tealLight,
                padding: '2px 10px', borderRadius: 10,
              }}>
                {sortedTopics.length} 个话题
              </span>
            </div>
            {sortedTopics.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 60, color: T.gray400, fontSize: 13 }}>
                暂无趋势数据，请先触发趋势快照
              </div>
            ) : sortedTopics.map((topic, i) => (
              <TopicRow
                key={topic.key}
                topic={topic}
                dates={dates}
                maxCount={maxCount}
                color={COLORS[i % COLORS.length]}
                isLast={i === sortedTopics.length - 1}
              />
            ))}
          </>
        ) : (
          /* ── Keywords tab ── */
          <>
            <div style={{
              padding: '14px 20px', borderBottom: `1px solid ${T.gray100}`,
              background: `linear-gradient(135deg, ${T.purple}06, ${T.purple}02)`,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: T.gray900 }}>
                关键词频率（近{days}天）
              </span>
              <span style={{
                marginLeft: 'auto', fontSize: 11, fontWeight: 600,
                color: T.purple, background: T.purpleLight,
                padding: '2px 10px', borderRadius: 10,
              }}>
                {keywords.length} 个热词
              </span>
            </div>
            <div style={{ padding: '20px 24px' }}>
              {keywords.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: T.gray400, fontSize: 13 }}>暂无关键词数据</div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {keywords.map((kw, i) => {
                    const ratio = kw.count / (keywords[0]?.count || 1);
                    const fontSize = Math.max(12, Math.round(12 + ratio * 14));
                    const color = COLORS[i % COLORS.length];
                    return (
                      <span
                        key={kw.keyword}
                        style={{
                          fontSize, fontWeight: ratio > 0.5 ? 700 : 400,
                          color, padding: '4px 12px', borderRadius: T.radiusXs,
                          background: `${color}08`,
                          border: `1px solid ${color}20`,
                          cursor: 'default', transition: 'all 0.15s',
                        }}
                        title={`${kw.keyword}: ${kw.count}次`}
                        onMouseEnter={(e) => { e.currentTarget.style.background = `${color}18`; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = `${color}08`; }}
                      >
                        {kw.keyword}
                        <span style={{ fontSize: 10, color: T.gray400, marginLeft: 4 }}>{kw.count}</span>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
