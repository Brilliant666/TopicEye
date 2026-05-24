'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAppContext } from '@/components/ClientLayout';
import { motherTopicsApi, contentsApi, type MotherTopic, type ContentItem } from '@/lib/api';

/* ── helpers ── */

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? '#10b981' :
    score >= 65 ? '#f59e0b' :
    score >= 50 ? '#6b7280' :
    '#9ca3af';
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
      {score.toFixed(1)}
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
  const pct = Math.min(100, (score / 120) * 100);
  const color = score >= 80 ? '#10b981' : score >= 65 ? '#f59e0b' : '#9ca3af';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        flex: 1,
        height: 4,
        borderRadius: 2,
        background: '#f3f4f6',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: 2,
        }} />
      </div>
    </div>
  );
}

/* ── Content Card ── */

interface ScoredContent {
  content: ContentItem;
  scoring: {
    final_score: number;
    top_topic: string | null;
    topic_scores: Array<{ name: string; keyword_score: number; weight: number; final: number }>;
  } | null;
}

function ContentCard({ item, onToggle }: { item: ScoredContent; onToggle: (id: number) => void }) {
  const { favorites } = useAppContext();
  const fav = favorites?.[item.content.id];
  const score = item.scoring?.final_score ?? 0;
  const topTopic = item.scoring?.top_topic;

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <ScoreBadge score={score} />
            {topTopic && <TopicPill name={topTopic} active={true} />}
            <span style={{ fontSize: 11, color: '#9ca3af' }}>
              {item.content.source_name || item.content.source || ''}
            </span>
          </div>
          <a
            href={item.content.url || item.content.original_url || '#'}
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
          onClick={() => onToggle(item.content.id!)}
          title={fav ? '取消收藏' : '收藏'}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 18,
            padding: '2px 6px',
            color: fav ? '#f59e0b' : '#d1d5db',
            flexShrink: 0,
          }}
        >
          ★
        </button>
      </div>

      {/* score detail */}
      {item.scoring && (
        <div style={{ marginBottom: 8 }}>
          <ScoreBar score={score} />
          <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
            {item.scoring.topic_scores.slice(0, 4).map(ts => (
              <span key={ts.name} style={{ fontSize: 11, color: '#6b7280' }}>
                {ts.name}: <b style={{ color: ts.final > 0.5 ? '#374151' : '#9ca3af' }}>{ts.final.toFixed(2)}</b>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* meta */}
      <div style={{ display: 'flex', gap: 12, fontSize: 12, color: '#9ca3af' }}>
        {item.content.curation_score != null && (
          <span>精选分 {item.content.curation_score.toFixed(1)}</span>
        )}
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
  const [selectedTopic, setSelectedTopic] = useState<string>(''); // '' = all
  const [contents, setContents] = useState<ScoredContent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterMinScore, setFilterMinScore] = useState(0);
  const { toggleFavorite } = useAppContext();

  // Load mother topics
  useEffect(() => {
    motherTopicsApi.list(true).then(setTopics).catch(console.error);
  }, []);

  // Load contents and score them
  useEffect(() => {
    if (!topics.length) return;
    setLoading(true);

    contentsApi
      .list({ page: 1, page_size: 100, category: selectedTopic || undefined })
      .then(async ({ items }) => {
        const scored: ScoredContent[] = await Promise.all(
          items.map(async content => {
            try {
              const scoring = await motherTopicsApi.score({
                title: content.title,
                summary: content.summary || '',
                hot_value: (content.metrics as any)?.hot_value || 0,
              });
              return { content, scoring };
            } catch {
              return { content, scoring: null };
            }
          })
        );

        // Sort by final score desc
        scored.sort((a, b) => (b.scoring?.final_score ?? 0) - (a.scoring?.final_score ?? 0));
        setContents(scored);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [topics, selectedTopic]);

  const filtered = contents.filter(c => (c.scoring?.final_score ?? 0) >= filterMinScore);

  return (
    <div style={{ padding: '20px 24px', maxWidth: 900 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#111827', marginBottom: 4 }}>
          📌 我的母题
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
            {filterMinScore.toFixed(0)}
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
          <div style={{ fontSize: 20, fontWeight: 700, color: '#111827' }}>{filtered.length}</div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>候选内容</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#10b981' }}>
            {filtered.filter(c => (c.scoring?.final_score ?? 0) >= 80).length}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>今日主选题</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}>
            {filtered.filter(c => {
              const s = c.scoring?.final_score ?? 0;
              return s >= 65 && s < 80;
            }).length}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>值得储备</div>
        </div>
        <div style={{ borderLeft: '1px solid #e5e7eb', paddingLeft: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#6366f1' }}>
            {topics.find(t => t.name === selectedTopic)?.keywords.length ?? 0}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af' }}>关键词</div>
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
          去配置 →
        </a>
      </div>
    </div>
  );
}