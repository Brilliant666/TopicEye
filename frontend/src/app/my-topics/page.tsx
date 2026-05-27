'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { ArrowRight, Pin, Star } from 'lucide-react';
import { useAppContext } from '@/components/ClientLayout';
import { motherTopicsApi, contentsApi, type MotherTopic, type ContentItem } from '@/lib/api';

/* ── helpers ── */

function normalizeScore(raw: number): number {
  // 理论上限 1.1，归一化到 0-100
  return Math.min(Math.round(raw * (100 / 1.1)), 100);
}

function ScoreBadge({ score }: { score: number }) {
  const s = normalizeScore(score);
  const color = s >= 80 ? '#10b981' : s >= 65 ? '#f59e0b' : s >= 50 ? '#6b7280' : '#9ca3af';
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 8px',
      borderRadius: 12,
      fontSize: 11,
      fontWeight: 700,
      color: '#fff',
      background: color,
      minWidth: 36,
      textAlign: 'center',
    }}>
      {s}
    </span>
  );
}

function TopicPill({ name, active }: { name: string; active: boolean }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      fontSize: 12,
      fontWeight: 500,
      border: `1px solid ${active ? '#6366f1' : '#e5e7eb'}`,
      color: active ? '#6366f1' : '#6b7280',
      background: active ? '#eef2ff' : '#fff',
    }}>
      {name}
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const s = normalizeScore(score);
  const pct = Math.min(100, s);
  const color = s >= 80 ? '#10b981' : s >= 65 ? '#f59e0b' : '#9ca3af';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: '#f3f4f6', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, color: '#9ca3af', minWidth: 28 }}>{s}分</span>
    </div>
  );
}

/* ── Content Card ── */

interface TopicScore {
  name: string;
  keyword_score: number;
  weight: number;
  freshness: number;
  final: number;
}

interface ScoredContent {
  content: ContentItem;
  scoring: {
    final_score: number;
    top_topic: string | null;
    topic_scores: TopicScore[];
  } | null;
}

function ContentCard({ item, onToggle }: { item: ScoredContent; onToggle: (id: number) => void }) {
  const { favorites } = useAppContext();
  const fav = favorites.has(item.content.id);
  const score = item.scoring?.final_score ?? 0;
  const topTopic = item.scoring?.top_topic;
  const allTopics = item.scoring?.topic_scores ?? [];

  // 过滤出得分 > 0 的母题，展示所有匹配的
  const matchedTopics = allTopics.filter(ts => ts.final > 0);

  return (
    <div style={{
      border: '1px solid #f3f4f6',
      borderRadius: 10,
      padding: '14px 16px',
      marginBottom: 10,
      background: '#fff',
      position: 'relative',
    }}>
      {/* header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
            <ScoreBadge score={score} />
            {matchedTopics.map(ts => (
              <TopicPill
                key={ts.name}
                name={ts.name}
                active={ts.name === topTopic}
              />
            ))}
            <span style={{ fontSize: 11, color: '#9ca3af' }}>
              {item.content.source_name || ''}
            </span>
          </div>
          <a
            href={item.content.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: '#111827',
              textDecoration: 'none',
              lineHeight: 1.5,
              display: 'block',
            }}
          >
            {item.content.title}
          </a>
        </div>
        <button
          onClick={() => onToggle(item.content.id)}
          title={fav ? '取消收藏' : '收藏'}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 6px',
            color: fav ? '#f59e0b' : '#d1d5db',
            flexShrink: 0,
            display: 'inline-flex',
            alignItems: 'center',
          }}
        >
          <Star size={18} strokeWidth={2} fill={fav ? '#f59e0b' : 'none'} />
        </button>
      </div>

      {/* score detail */}
      {item.scoring && matchedTopics.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <ScoreBar score={score} />
          <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
            {matchedTopics.map(ts => (
              <span key={ts.name} style={{ fontSize: 11, color: '#6b7280' }}>
                {ts.name}: <b style={{ color: ts.final > 50 ? '#374151' : '#9ca3af' }}>
                  {normalizeScore(ts.final)}分
                </b>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* meta */}
      <div style={{ display: 'flex', gap: 12, fontSize: 12, color: '#9ca3af' }}>
        {item.content.published_at && (
          <span>{new Date(item.content.published_at).toLocaleDateString('zh-CN')}</span>
        )}
        {item.content.author && <span>{item.content.author}</span>}
      </div>
    </div>
  );
}

/* ── Main Page ── */

export default function MyTopicsPage() {
  const [topics, setTopics] = useState<MotherTopic[]>([]);
  const [allScored, setAllScored] = useState<ScoredContent[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string>(''); // '' = 全部
  const [loading, setLoading] = useState(true);
  const [filterMinScore, setFilterMinScore] = useState(0);
  const { toggleFavorite } = useAppContext();

  // Load mother topics + fetch all contents once, then batch score
  useEffect(() => {
    setLoading(true);
    Promise.all([
      motherTopicsApi.list(true),
      contentsApi.list({ page: 1, page_size: 200 }),
    ]).then(async ([ts, { items }]) => {
      setTopics(ts);

      // Batch score all items in a single API call
      let scored: ScoredContent[];
      try {
        const { results } = await motherTopicsApi.scoreBatch(
          items.map(c => ({
            title: c.title,
            summary: c.summary || '',
            hot_value: 0,
          }))
        );
        // Map results back to ScoredContent[], matching by title
        const resultMap = new Map(results.map(r => [r.title, r]));
        scored = items.map(content => ({
          content,
          scoring: resultMap.get(content.title) ?? null,
        }));
      } catch {
        scored = items.map(content => ({ content, scoring: null }));
      }

      // Sort by final score desc
      scored.sort((a, b) =>
        (b.scoring?.final_score ?? 0) - (a.scoring?.final_score ?? 0)
      );
      setAllScored(scored);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  // Derive displayed items: filter by selected topic, then by min score
  const filtered = allScored.filter(c => {
    const s = c.scoring?.final_score ?? 0;

    // 全部模式下：至少要有母题匹配分（score > 0）才展示
    if (!selectedTopic) {
      return s > 0;  // 过滤掉score=0的无关联内容
    }

    if (s < filterMinScore / 100) return false;
    return c.scoring?.top_topic === selectedTopic;
  });

  // Stats from full scored set (unfiltered by min score)
  const statsTotal = allScored.length;
  const statsMain = allScored.filter(c => normalizeScore(c.scoring?.final_score ?? 0) >= 80).length;
  const statsReserve = allScored.filter(c => {
    const s = normalizeScore(c.scoring?.final_score ?? 0);
    return s >= 65 && s < 80;
  }).length;

  return (
    <div style={{ padding: '20px 24px', maxWidth: 900 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#111827', marginBottom: 4 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Pin size={20} color="#6366f1" strokeWidth={2.1} />
            我的母题
          </span>
        </h1>
        <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
          根据你的公众号定位精选的内容，只展示匹配母题的高质量候选
        </p>
      </div>

      {/* Topic tabs */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 20,
        borderBottom: '1px solid #f3f4f6',
        paddingBottom: 12,
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        <button
          onClick={() => setSelectedTopic('')}
          style={{
            padding: '5px 14px',
            borderRadius: 16,
            border: 'none',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
            background: selectedTopic === '' ? '#111827' : '#f3f4f6',
            color: selectedTopic === '' ? '#fff' : '#374151',
          }}
        >
          全部
        </button>
        {topics.map(t => (
          <button
            key={t.id}
            onClick={() => setSelectedTopic(t.name)}
            style={{
              padding: '5px 14px',
              borderRadius: 16,
              border: 'none',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              background: selectedTopic === t.name ? '#6366f1' : '#f3f4f6',
              color: selectedTopic === t.name ? '#fff' : '#374151',
            }}
          >
            {t.name}
          </button>
        ))}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: '#6b7280' }}>最低得分</span>
          <input
            type="range"
            min={0}
            max={100}
            value={filterMinScore}
            onChange={e => setFilterMinScore(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', minWidth: 30 }}>
            {filterMinScore}
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div style={{
        display: 'flex',
        gap: 16,
        marginBottom: 20,
        padding: '12px 16px',
        background: '#f9fafb',
        borderRadius: 10,
      }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#111827' }}>{statsTotal}</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>候选内容</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#10b981' }}>{statsMain}</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>今日主选题</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}>{statsReserve}</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>值得储备</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#6366f1' }}>{topics.length}</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>母题数</div>
        </div>
      </div>

      {/* Content list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#9ca3af' }}>
          正在按母题打分...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#9ca3af' }}>
          暂无匹配内容，试试降低最低得分阈值
        </div>
      ) : (
        <div>
          {filtered.map(item => (
            <ContentCard
              key={item.content.id}
              item={item}
              onToggle={toggleFavorite}
            />
          ))}
        </div>
      )}

      {/* Settings link */}
      <div style={{
        marginTop: 32,
        padding: '12px 16px',
        background: '#f0f1ff',
        borderRadius: 10,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#3730a3' }}>母题配置</div>
          <div style={{ fontSize: 12, color: '#6366f1', marginTop: 2 }}>
            管理四个母题的关键词，调整匹配精准度
          </div>
        </div>
        <a
          href="/mother-topics/config"
          style={{
            padding: '6px 16px',
            borderRadius: 8,
            background: '#6366f1',
            color: '#fff',
            textDecoration: 'none',
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            去配置
            <ArrowRight size={14} strokeWidth={2} />
          </span>
        </a>
      </div>
    </div>
  );
}
