'use client';

import React, { useState, useEffect } from 'react';
import { T } from '@/lib/design-tokens';
import { statsApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import Header from '@/components/Header';

interface DashboardData {
  kpi: {
    total_crawled: number;
    total_curated: number;
    avg_curation: number;
    active_sources: number;
  };
  source_breakdown: Array<{
    source_name: string;
    source_type: string;
    content_count: number;
    curated_count: number;
    avg_score: number;
  }>;
  daily_trend: Array<{
    date: string;
    content_count: number;
    curated_count: number;
    avg_curation: number;
  }>;
}

const SOURCE_TYPE_COLOR: Record<string, string> = {
  rss: T.teal,
  hackernews: T.purple,
  api: T.primary,
  unknown: T.gray400,
};

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{
      width: '100%',
      height: 8,
      background: T.gray200,
      borderRadius: 4,
      overflow: 'hidden',
    }}>
      <div style={{
        width: `${pct}%`,
        height: '100%',
        background: color,
        borderRadius: 4,
        transition: 'width 0.3s',
      }} />
    </div>
  );
}

function TrendChart({ data }: { data: DashboardData['daily_trend'] }) {
  if (!data || data.length === 0) return <p style={{ color: T.gray400, fontSize: 13 }}>暂无趋势数据</p>;

  const maxCount = Math.max(...data.map(d => d.content_count), 1);

  return (
    <div>
      {/* Chart */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 80, marginBottom: 8 }}>
        {data.map((day, i) => {
          const pct = (day.content_count / maxCount) * 100;
          return (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 11, color: T.gray400, fontFamily: T.mono }}>{day.content_count}</span>
              <div style={{
                width: '100%',
                height: `${pct}%`,
                background: i === data.length - 1 ? T.primary : T.gray300,
                borderRadius: '3px 3px 0 0',
                minHeight: 4,
              }} />
            </div>
          );
        })}
      </div>
      {/* Labels */}
      <div style={{ display: 'flex', gap: 8 }}>
        {data.map((day, i) => {
          const d = new Date(day.date + 'T00:00:00');
          const label = `${d.getMonth() + 1}/${d.getDate()}`;
          return (
            <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: T.gray400 }}>
              {label}
            </div>
          );
        })}
      </div>
      {/* Avg curation row */}
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        {data.map((day, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, color: T.gray400 }}>
            均值 {day.avg_curation || '-'}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function StatsPage() {
  const { topicCount } = useAppContext();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const result = await statsApi.getDashboard(days);
        setData(result);
      } catch (e: any) {
        setError(e?.message || '加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [days]);

  const kpi = data?.kpi;
  const curatedRate = kpi && kpi.total_crawled > 0
    ? Math.round((kpi.total_curated / kpi.total_crawled) * 100)
    : 0;

  const dateStr = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <div style={{ maxWidth: 820, margin: '0 auto', padding: '24px 20px' }}>
        <Header
          title="数据统计"
          subtitle={`统计周期：最近 ${days} 天`}
          date={dateStr}
        />

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
        </div>

        {loading && (
          <div style={{ textAlign: 'center', padding: 40, color: T.gray400 }}>加载中...</div>
        )}

        {error && (
          <div style={{ padding: 16, background: T.redLight, borderRadius: 8, color: T.red, fontSize: 13 }}>
            {error}
          </div>
        )}

        {data && !loading && (
          <>
            {/* ── KPI Cards ── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
              {[
                { label: '总采集', value: kpi?.total_crawled ?? 0, unit: '条', color: T.gray600 },
                { label: '精选内容', value: kpi?.total_curated ?? 0, unit: '条', color: T.primary },
                { label: '精选率', value: curatedRate, unit: '%', color: T.teal },
                { label: '活跃信源', value: kpi?.active_sources ?? 0, unit: '个', color: T.purple },
              ].map(card => (
                <div key={card.label} style={{
                  background: T.white,
                  border: `1px solid ${T.gray200}`,
                  borderRadius: 12,
                  padding: '16px 18px',
                }}>
                  <div style={{ fontSize: 12, color: T.gray500, marginBottom: 6 }}>{card.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: card.color, fontFamily: T.mono, lineHeight: 1.1 }}>
                    {card.value}
                    <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 2, color: T.gray400 }}>{card.unit}</span>
                  </div>
                  <div style={{ fontSize: 11, color: T.gray400, marginTop: 4 }}>
                    均分 <span style={{ fontFamily: T.mono }}>{kpi?.avg_curation ?? '-'} </span>
                  </div>
                </div>
              ))}
            </div>

            {/* ── Daily Trend ── */}
            <div style={{
              background: T.white,
              border: `1px solid ${T.gray200}`,
              borderRadius: 12,
              padding: 20,
              marginBottom: 20,
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.gray700, marginBottom: 16 }}>
                每日采集趋势
              </div>
              <TrendChart data={data.daily_trend} />
            </div>

            {/* ── Source Breakdown ── */}
            <div style={{
              background: T.white,
              border: `1px solid ${T.gray200}`,
              borderRadius: 12,
              padding: 20,
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.gray700, marginBottom: 16 }}>
                信源明细
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.gray200}` }}>
                    {['信源', '类型', '采集量', '精选量', '精选率', '均分', '质量条'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '6px 8px', color: T.gray400, fontWeight: 400, fontSize: 12 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.source_breakdown.map((src, i) => {
                    const rate = src.content_count > 0
                      ? Math.round((src.curated_count / src.content_count) * 100)
                      : 0;
                    const color = SOURCE_TYPE_COLOR[src.source_type] || T.gray400;
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${T.gray100}` }}>
                        <td style={{ padding: '10px 8px', fontWeight: 500, color: T.gray800 }}>{src.source_name}</td>
                        <td style={{ padding: '10px 8px' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: 10,
                            fontSize: 11,
                            background: color + '20',
                            color: color,
                          }}>
                            {src.source_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', fontFamily: T.mono, color: T.gray600 }}>{src.content_count}</td>
                        <td style={{ padding: '10px 8px', fontFamily: T.mono, color: T.primary }}>{src.curated_count}</td>
                        <td style={{ padding: '10px 8px', fontFamily: T.mono, color: T.teal }}>{rate}%</td>
                        <td style={{ padding: '10px 8px', fontFamily: T.mono, color: T.gray500 }}>{src.avg_score || '-'}</td>
                        <td style={{ padding: '10px 8px', width: 100 }}>
                          <MiniBar value={src.curated_count} max={Math.max(...data.source_breakdown.map(s => s.curated_count), 1)} color={T.primary} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
