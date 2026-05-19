'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';
import { contentsApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';
import { getRecommendLevel } from '@/types';

function parseUTC(s: string): Date {
  const normalized = s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s) ? s : s + 'Z';
  return new Date(normalized);
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = parseUTC(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const hours = Math.floor(diffMs / 3600000);
  if (hours < 1) return '刚刚';
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return `${Math.floor(days / 30)} 个月前`;
}

export default function FavoritesPage() {
  const { favorites, toggleFavorite } = useAppContext();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAnalysis, setSelectedAnalysis] = useState<ContentAnalysis | null>(null);

  const fetchFavorites = useCallback(async () => {
    try {
      setLoading(true);
      const res = await contentsApi.listFavorites({ page_size: 100 });
      const data = res as any;
      setItems(data.items || []);
    } catch (err) {
      console.error('Failed to fetch favorites:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFavorites();
  }, [fetchFavorites]);

  const handleUnfav = async (id: number) => {
    await toggleFavorite(id);
    setItems((prev) => prev.filter((item) => item.id !== id));
  };

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900, marginBottom: 6 }}>收藏夹</h1>
        <p style={{ fontSize: 13, color: T.gray400 }}>
          已收藏 <b style={{ color: T.primary, fontFamily: T.mono }}>{items.length}</b> 条内容
        </p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.3 }}>☆</div>
          <div>还没有收藏任何内容</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>在今日选题中点击星标即可收藏</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: 40 }}>
          {items.map((item) => {
            const analysis = item.analysis as ContentAnalysis | null;
            const recommend = analysis ? getRecommendLevel(analysis.creator_score, analysis.viral_score, analysis.risk_score) : null;
            return (
              <div
                key={item.id}
                style={{
                  background: T.white,
                  borderRadius: T.radius,
                  border: `1px solid ${T.gray100}`,
                  padding: '20px 24px',
                  cursor: analysis ? 'pointer' : 'default',
                  transition: 'box-shadow 0.15s',
                }}
                onClick={() => analysis && setSelectedAnalysis(analysis)}
                onMouseEnter={(e) => (e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.boxShadow = 'none')}
              >
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ fontSize: 11, color: T.gray400 }}>{item.source_name}</span>
                      <span style={{ fontSize: 11, color: T.gray300 }}>·</span>
                      <span style={{ fontSize: 11, color: T.gray400 }}>{item.category}</span>
                      <span style={{ fontSize: 11, color: T.gray300 }}>·</span>
                      <span style={{ fontSize: 11, color: T.gray400 }}>{timeAgo(item.published_at || item.crawled_at)}</span>
                    </div>
                    <h3 style={{ fontSize: 15, fontWeight: 600, color: T.gray900, lineHeight: 1.5 }}>
                      {item.title}
                    </h3>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleUnfav(item.id); }}
                    style={{
                      background: 'none',
                      border: 'none',
                      fontSize: 18,
                      cursor: 'pointer',
                      color: '#F59E0B',
                      padding: '4px 8px',
                      lineHeight: 1,
                    }}
                    title="取消收藏"
                  >
                    ★
                  </button>
                </div>

                {/* Scores */}
                {analysis && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <ScoreBadge label="创作" value={analysis.creator_score} color={T.primary} />
                    <ScoreBadge label="爆文" value={analysis.viral_score} color="#F59E0B" />
                    <ScoreBadge label="质量" value={analysis.quality_score} color="#10B981" />
                    {recommend && (
                      <span style={{
                        fontSize: 11,
                        fontWeight: 500,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: recommend.bg,
                        color: recommend.color,
                      }}>
                        {recommend.label}
                      </span>
                    )}
                  </div>
                )}

                {/* Summary */}
                {analysis?.summary && (
                  <p style={{ fontSize: 13, color: T.gray500, marginTop: 8, lineHeight: 1.6 }}>
                    {analysis.summary}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Analysis panel overlay */}
      {selectedAnalysis && (
        <>
          <div
            onClick={() => setSelectedAnalysis(null)}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 999 }}
          />
          <div style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, maxWidth: '90vw',
            background: T.white, boxShadow: '-4px 0 24px rgba(0,0,0,0.1)', zIndex: 1000,
            overflowY: 'auto', padding: 32,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: T.gray900 }}>AI 分析报告</h2>
              <button
                onClick={() => setSelectedAnalysis(null)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: T.gray400, padding: 4 }}
              >
                ✕
              </button>
            </div>

            {/* Scores */}
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 12 }}>多维评分</h3>
              {[
                { label: '质量', value: selectedAnalysis.quality_score, color: '#10B981' },
                { label: '热度', value: selectedAnalysis.hot_score, color: '#EF4444' },
                { label: '新鲜度', value: selectedAnalysis.freshness_score, color: '#3B82F6' },
                { label: '创作价值', value: selectedAnalysis.creator_score, color: T.primary },
                { label: '爆文潜力', value: selectedAnalysis.viral_score, color: '#F59E0B' },
                { label: '风险', value: selectedAnalysis.risk_score, color: '#6B7280' },
              ].map((s) => (
                <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: T.gray500, width: 56 }}>{s.label}</span>
                  <div style={{ flex: 1, height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${s.value}%`, height: '100%', background: s.color, borderRadius: 3 }} />
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.gray700, width: 24, textAlign: 'right' }}>{Math.round(s.value)}</span>
                </div>
              ))}
            </div>

            {/* Summary */}
            {selectedAnalysis.summary && (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>内容摘要</h3>
                <p style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7 }}>{selectedAnalysis.summary}</p>
              </div>
            )}

            {/* Key Points */}
            {selectedAnalysis.key_points?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>核心观点</h3>
                {selectedAnalysis.key_points.map((point, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 8, paddingLeft: 12, borderLeft: `3px solid ${T.primary}` }}>
                    <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{point}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Creator Angles */}
            {selectedAnalysis.creator_angles?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>创作角度</h3>
                {selectedAnalysis.creator_angles.map((angle, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 8, paddingLeft: 12, borderLeft: `3px solid #10B981` }}>
                    <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{angle}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Title Suggestions */}
            {selectedAnalysis.title_suggestions?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>建议标题</h3>
                {selectedAnalysis.title_suggestions.map((title, i) => (
                  <div key={i} style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7, marginBottom: 6 }}>
                    <span style={{ color: T.primary, fontWeight: 600 }}>{i + 1}.</span> {title}
                  </div>
                ))}
              </div>
            )}

            {/* Recommended Reason */}
            {selectedAnalysis.recommended_reason && (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>推荐理由</h3>
                <p style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7, padding: 12, background: T.gray50, borderRadius: 8 }}>
                  {selectedAnalysis.recommended_reason}
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Score Badge ───

function ScoreBadge({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <span style={{ fontSize: 11, color: T.gray500 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 700, color }}>{Math.round(value)}</span>
    </div>
  );
}
