'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  ExternalLink,
  Hash,
  Layers3,
  Loader2,
  Radio,
  Sparkles,
  Tags,
  Target,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';

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

interface TopicSeries {
  key: string;
  name: string;
  pts: TrendPoint[];
  total: number;
  picks: number;
  latestCount: number;
  previousCount: number;
  delta: number;
  momentum: number;
  maxScore: number;
  topItems: { title: string; url: string; score: number }[];
}

const COLORS = [
  T.primary,
  T.teal,
  '#3B82F6',
  T.amber,
  '#10B981',
  '#EF4444',
  T.purple,
  '#06B6D4',
  '#64748B',
  '#EC4899',
];

function Sparkline({
  data,
  color = T.primary,
  width = 132,
  height = 42,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (data.length < 2) {
    return <span style={{ fontSize: 11, color: T.gray300 }}>-</span>;
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const points = data.map((value, index) => {
    const x = index * step;
    const y = height - 5 - ((value - min) / range) * (height - 12);
    return `${x},${y}`;
  });
  const area = `${points.join(' ')} ${width},${height} 0,${height}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      <polygon points={area} fill={`${color}14`} />
      <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MiniBars({
  dates,
  counts,
  color,
  maxCount,
}: {
  dates: string[];
  counts: number[];
  color: string;
  maxCount: number;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(dates.length, 1)}, minmax(0, 1fr))`, gap: 5, alignItems: 'end', height: 58 }}>
      {dates.map((date, index) => {
        const count = counts[index] || 0;
        const height = count ? Math.max(8, (count / maxCount) * 50) : 3;
        return (
          <div key={date} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', minWidth: 0, height: 58 }}>
            <div
              title={`${date}: ${count} 条`}
              style={{
                height,
                borderRadius: '5px 5px 2px 2px',
                background: count ? color : T.gray200,
                opacity: count ? 0.82 : 0.45,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  color,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  hint: string;
  color: string;
}) {
  return (
    <div style={{
      background: T.white,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      padding: '15px 16px',
      minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Icon size={15} color={color} strokeWidth={2.2} />
        <span style={{ fontSize: 12, color: T.gray500, fontWeight: 800 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, lineHeight: 1, fontWeight: 900, fontFamily: T.mono, color: T.gray900 }}>{value}</div>
      <div style={{ marginTop: 6, fontSize: 11, color: T.gray400 }}>{hint}</div>
    </div>
  );
}

function MomentumBadge({ delta }: { delta: number }) {
  const rising = delta > 0;
  const flat = delta === 0;
  const color = flat ? T.gray500 : rising ? T.primary : T.teal;
  const bg = flat ? T.gray100 : rising ? T.primaryLight : T.tealLight;
  const Icon = flat ? Activity : rising ? ArrowUpRight : ArrowDownRight;

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 11,
      fontWeight: 900,
      color,
      background: bg,
      border: `1px solid ${flat ? T.gray200 : rising ? T.primaryBorder : T.tealBorder}`,
      borderRadius: 999,
      padding: '3px 8px',
      whiteSpace: 'nowrap',
    }}>
      <Icon size={12} strokeWidth={2.4} />
      {flat ? '持平' : `${rising ? '+' : ''}${delta}`}
    </span>
  );
}

function TopicCard({
  topic,
  dates,
  maxCount,
  color,
  rank,
}: {
  topic: TopicSeries;
  dates: string[];
  maxCount: number;
  color: string;
  rank: number;
}) {
  const counts = dates.map((date) => topic.pts.find((point) => point.date === date)?.content_count || 0);

  return (
    <article style={{
      background: T.white,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      overflow: 'hidden',
      boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
    }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '42px minmax(0, 1fr) auto',
        gap: 12,
        alignItems: 'start',
        padding: '17px 18px 12px',
      }}>
        <div style={{
          width: 32,
          height: 32,
          borderRadius: T.radiusSm,
          background: `${color}14`,
          color,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          fontWeight: 900,
          fontFamily: T.mono,
        }}>
          {rank}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 5 }}>
            <h2 style={{ fontSize: 16, lineHeight: 1.35, fontWeight: 900, color: T.gray900 }}>
              {topic.name}
            </h2>
            <MomentumBadge delta={topic.delta} />
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 11, color: T.gray400 }}>
            <span>{topic.total} 条内容</span>
            <span>{topic.picks} 条精选</span>
            <span>峰值 {Math.round(topic.maxScore)}</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 26, lineHeight: 1, fontWeight: 900, fontFamily: T.mono, color }}>
            {topic.latestCount}
          </div>
          <div style={{ fontSize: 10, color: T.gray400, marginTop: 4 }}>LATEST</div>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '150px minmax(0, 1fr)',
        gap: 18,
        alignItems: 'end',
        padding: '0 18px 15px 72px',
      }}>
        <Sparkline data={counts} color={color} />
        <MiniBars dates={dates} counts={counts} color={color} maxCount={maxCount} />
      </div>

      {topic.topItems.length > 0 && (
        <div style={{ borderTop: `1px solid ${T.gray100}`, padding: '10px 18px 13px 72px', display: 'flex', flexDirection: 'column', gap: 7 }}>
          {topic.topItems.slice(0, 2).map((item, index) => (
            <a
              key={`${item.title}-${index}`}
              href={item.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                color: T.gray600,
                textDecoration: 'none',
                fontSize: 12,
                lineHeight: 1.5,
              }}
            >
              <span style={{ width: 5, height: 5, borderRadius: 999, background: color, flexShrink: 0 }} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</span>
              <span style={{ color, fontWeight: 900, fontFamily: T.mono }}>{Math.round(item.score)}</span>
              <ExternalLink size={12} color={T.gray400} />
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

function KeywordBoard({ keywords }: { keywords: KeywordItem[] }) {
  if (keywords.length === 0) {
    return <EmptyState title="暂无关键词数据" desc="等待趋势快照生成后会出现关键词频率。" />;
  }

  const max = keywords[0]?.count || 1;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
      {keywords.slice(0, 48).map((keyword, index) => {
        const ratio = keyword.count / max;
        const color = COLORS[index % COLORS.length];
        return (
          <div key={keyword.keyword} style={{
            background: T.white,
            border: `1px solid ${T.gray200}`,
            borderRadius: T.radius,
            padding: '13px 14px',
            minWidth: 0,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontSize: 14, fontWeight: 900, color: T.gray900, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {keyword.keyword}
              </span>
              <span style={{ fontSize: 12, fontWeight: 900, color, fontFamily: T.mono }}>{keyword.count}</span>
            </div>
            <div style={{ height: 7, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ width: `${Math.max(8, Math.round(ratio * 100))}%`, height: '100%', background: color, borderRadius: 999 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ControlPanel({
  days,
  setDays,
  activeTab,
  setActiveTab,
}: {
  days: number;
  setDays: (days: number) => void;
  activeTab: 'topics' | 'keywords';
  setActiveTab: (tab: 'topics' | 'keywords') => void;
}) {
  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
      <PanelTitle icon={CalendarDays} title="观察窗口" />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 5, background: T.gray100, padding: 4, borderRadius: T.radiusSm, marginBottom: 14 }}>
        {[3, 7, 14, 30].map((value) => {
          const active = days === value;
          return (
            <button
              key={value}
              onClick={() => setDays(value)}
              style={{
                border: 'none',
                borderRadius: T.radiusXs,
                background: active ? T.white : 'transparent',
                color: active ? T.primary : T.gray500,
                boxShadow: active ? '0 1px 3px rgba(15,23,42,0.08)' : 'none',
                padding: '6px 0',
                fontSize: 11,
                fontWeight: active ? 900 : 700,
                cursor: 'pointer',
              }}
            >
              {value}天
            </button>
          );
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {[
          { key: 'topics' as const, label: '话题曲线', icon: BarChart3 },
          { key: 'keywords' as const, label: '关键词频率', icon: Tags },
        ].map((item) => {
          const Icon = item.icon;
          const active = activeTab === item.key;
          return (
            <button
              key={item.key}
              onClick={() => setActiveTab(item.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                background: active ? T.primaryLight : T.white,
                color: active ? T.primary : T.gray600,
                borderRadius: T.radiusSm,
                padding: '8px 10px',
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              <Icon size={14} />
              {item.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function KeywordPanel({ keywords }: { keywords: KeywordItem[] }) {
  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
      <PanelTitle icon={Hash} title="高频热词" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
        {keywords.slice(0, 18).map((keyword, index) => {
          const color = COLORS[index % COLORS.length];
          return (
            <span key={keyword.keyword} style={{
              fontSize: 11,
              fontWeight: 800,
              color,
              background: `${color}10`,
              border: `1px solid ${color}22`,
              padding: '4px 8px',
              borderRadius: 999,
            }}>
              {keyword.keyword}
            </span>
          );
        })}
        {keywords.length === 0 && <span style={{ fontSize: 12, color: T.gray400 }}>暂无热词</span>}
      </div>
    </section>
  );
}

function SignalPanel({ topics }: { topics: TopicSeries[] }) {
  const rising = topics.filter((topic) => topic.delta > 0).length;
  const cooling = topics.filter((topic) => topic.delta < 0).length;
  const stable = topics.length - rising - cooling;
  const rows = [
    { label: '升温', value: rising, color: T.primary },
    { label: '降温', value: cooling, color: T.teal },
    { label: '稳定', value: stable, color: T.gray500 },
  ];

  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
      <PanelTitle icon={Radio} title="信号面板" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {rows.map((row) => (
          <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: row.color }} />
            <span style={{ flex: 1, fontSize: 12, color: T.gray600 }}>{row.label}</span>
            <span style={{ fontSize: 13, fontWeight: 900, color: T.gray900, fontFamily: T.mono }}>{row.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function PanelTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 13 }}>
      <Icon size={15} color={T.primary} strokeWidth={2.2} />
      <span style={{ fontSize: 14, fontWeight: 900, color: T.gray900 }}>{title}</span>
    </div>
  );
}

function EmptyState({ title, desc }: { title: string; desc: string }) {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: '64px 24px', textAlign: 'center' }}>
      <Sparkles size={34} color={T.gray300} style={{ marginBottom: 12 }} />
      <div style={{ fontSize: 15, fontWeight: 900, color: T.gray700 }}>{title}</div>
      <div style={{ marginTop: 6, fontSize: 12, color: T.gray400 }}>{desc}</div>
    </div>
  );
}

function buildTopicSeries(trends: TrendPoint[]): TopicSeries[] {
  const byTopic = new Map<string, { name: string; pts: TrendPoint[]; total: number; picks: number }>();
  for (const point of trends) {
    const key = `${point.topic_id}:${point.topic_name}`;
    if (!byTopic.has(key)) {
      byTopic.set(key, { name: point.topic_name, pts: [], total: 0, picks: 0 });
    }
    const entry = byTopic.get(key)!;
    entry.pts.push(point);
    entry.total += point.content_count;
    entry.picks += point.pick_count;
  }

  return Array.from(byTopic.entries()).map(([key, entry]) => {
    const pts = [...entry.pts].sort((a, b) => a.date.localeCompare(b.date));
    const latest = pts[pts.length - 1];
    const previous = pts[pts.length - 2];
    const latestCount = latest?.content_count || 0;
    const previousCount = previous?.content_count || 0;
    const maxScore = Math.max(...pts.map((point) => point.max_score || 0), 0);
    const topItems = pts
      .flatMap((point) => point.top_items || [])
      .sort((a, b) => b.score - a.score);
    return {
      key,
      name: entry.name,
      pts,
      total: entry.total,
      picks: entry.picks,
      latestCount,
      previousCount,
      delta: latestCount - previousCount,
      momentum: latestCount + Math.max(0, latestCount - previousCount) * 2 + entry.picks,
      maxScore,
      topItems,
    };
  }).sort((a, b) => b.momentum - a.momentum);
}

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
      const [topicResponse, keywordResponse] = await Promise.all([
        fetch(`${base}/trends/topics?days=${days}`),
        fetch(`${base}/trends/keywords?days=${days}&limit=60`),
      ]);
      if (topicResponse.ok) {
        const data = await topicResponse.json();
        setTrends(data.trends || []);
      }
      if (keywordResponse.ok) {
        const data = await keywordResponse.json();
        setKeywords(data.keywords || []);
      }
    } catch (err) {
      console.error('Failed to fetch trends:', err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void fetchData(); }, [fetchData]);

  const topicSeries = useMemo(() => buildTopicSeries(trends), [trends]);
  const sortedTopics = topicSeries.slice(0, 15);
  const dates = useMemo(() => Array.from(new Set(trends.map((trend) => trend.date))).sort(), [trends]);
  const maxCount = Math.max(...sortedTopics.flatMap((topic) => topic.pts.map((point) => point.content_count)), 1);
  const totalTopics = topicSeries.length;
  const totalPicks = trends.reduce((sum, trend) => sum + trend.pick_count, 0);
  const totalContent = trends.reduce((sum, trend) => sum + trend.content_count, 0);
  const topMomentum = sortedTopics[0]?.momentum || 0;

  return (
    <div className="fade-in" style={{
      minHeight: '100%',
      overflowY: 'auto',
      padding: '0 40px 48px',
      background: 'linear-gradient(180deg, #F8FAFC 0%, #F4F6F8 42%, #EEF2F5 100%)',
    }}>
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 4,
        margin: '0 -40px',
        padding: '18px 40px',
        background: 'rgba(248, 250, 252, 0.92)',
        borderBottom: `1px solid ${T.gray200}`,
        backdropFilter: 'blur(14px)',
      }}>
        <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ fontSize: 20, fontWeight: 900, color: T.gray900 }}>趋势追踪</h1>
              <span style={{
                fontSize: 10,
                fontWeight: 800,
                color: T.teal,
                background: T.tealLight,
                border: `1px solid ${T.tealBorder}`,
                padding: '3px 8px',
                borderRadius: 999,
                fontFamily: T.mono,
              }}>
                TREND LAB
              </span>
            </div>
            <p style={{ marginTop: 3, fontSize: 12, color: T.gray400 }}>
              追踪话题热度、精选转化和关键词信号
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: T.gray400, fontSize: 12 }}>
            <CalendarDays size={14} />
            近 <b style={{ color: T.teal, fontFamily: T.mono }}>{days}</b> 天
          </div>
        </div>
      </div>

      <div style={{
        maxWidth: 1180,
        margin: '24px auto 0',
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) 250px',
        gap: 16,
        alignItems: 'start',
      }}>
        <main style={{ minWidth: 0 }}>
          <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginBottom: 16 }}>
            <StatCard icon={Layers3} label="话题数" value={totalTopics} hint="进入追踪池" color={T.primary} />
            <StatCard icon={Target} label="精选内容" value={totalPicks} hint="被算法选中" color={T.amber} />
            <StatCard icon={Activity} label="内容总量" value={totalContent} hint="累计样本" color={T.teal} />
            <StatCard icon={Radio} label="最强动量" value={topMomentum} hint={sortedTopics[0]?.name || '暂无'} color={T.purple} />
          </section>

          {loading ? (
            <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 80, textAlign: 'center', color: T.gray400 }}>
              <Loader2 size={26} style={{ marginBottom: 12, opacity: 0.45 }} />
              <div style={{ fontSize: 14 }}>加载中...</div>
            </div>
          ) : activeTab === 'topics' ? (
            sortedTopics.length === 0 ? (
              <EmptyState title="暂无趋势数据" desc="趋势快照生成后会在这里展示话题曲线。" />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {sortedTopics.map((topic, index) => (
                  <TopicCard
                    key={topic.key}
                    topic={topic}
                    dates={dates}
                    maxCount={maxCount}
                    color={COLORS[index % COLORS.length]}
                    rank={index + 1}
                  />
                ))}
              </div>
            )
          ) : (
            <KeywordBoard keywords={keywords} />
          )}
        </main>

        <aside style={{ position: 'sticky', top: 88, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <ControlPanel days={days} setDays={setDays} activeTab={activeTab} setActiveTab={setActiveTab} />
          <SignalPanel topics={sortedTopics} />
          <KeywordPanel keywords={keywords} />
        </aside>
      </div>
    </div>
  );
}
