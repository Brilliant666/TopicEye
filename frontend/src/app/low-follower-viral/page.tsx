'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T, CATEGORIES } from '@/lib/design-tokens';
import { viralApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import CategoryChip from '@/components/CategoryChip';
import AnalysisPanel from '@/components/AnalysisPanel';
import type { ContentItem, ContentAnalysis } from '@/types';

const TIME_RANGES = [
  { value: 24, label: '24小时' },
  { value: 48, label: '48小时' },
  { value: 168, label: '7天' },
] as const;

export default function LowFollowerViralPage() {
  const { favorites, toggleFavorite } = useAppContext();

  const [items, setItems] = useState<ContentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hours, setHours] = useState<number>(48);
  const [category, setCategory] = useState('');
  const [selectedAnalysis, setSelectedAnalysis] = useState<(ContentAnalysis & { _content_id?: number }) | null>(null);
  const PAGE_SIZE = 20;

  const fetchItems = useCallback(async (p: number) => {
    try {
      setLoading(true);
      const res = await viralApi.list({ page: p, hours, category: category || undefined, page_size: PAGE_SIZE });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Failed to fetch LFV items:', err);
    } finally {
      setLoading(false);
    }
  }, [hours, category, page]);

  useEffect(() => { void fetchItems(1); }, [fetchItems]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setPage(1); }, [hours, category]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const startItem = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const endItem = Math.min(page * PAGE_SIZE, total);

  const getLfvScore = (item: ContentItem): number => {
    return (item as any)?.analysis?.adjusted_curation_score ?? (item as any)?.analysis?.curation_score ?? 0;
  };

  const getSourceWeight = (item: ContentItem): number => {
    return (item as any)?.analysis?.score_breakdown?.dimension_scores?.source_weight ?? 0;
  };

  const getObscureFactor = (item: ContentItem): number => {
    return (item as any)?.analysis?.score_breakdown?.dimension_scores?.obscure_factor ?? 0;
  };

  return (
    <div style={{ minHeight: '100vh', background: T.gray50 }}>
      {/* Header */}
      <div style={{
        background: T.white, borderBottom: `1px solid ${T.gray100}`,
        padding: '20px 28px 0',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: T.gray900, margin: 0 }}>
              低粉爆文发现 🔥
            </h1>
            <p style={{ fontSize: 13, color: T.gray500, margin: '4px 0 0' }}>
              找到小号高爆发内容 — 低粉丝作者发布的爆款选题
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {TIME_RANGES.map(tr => (
              <button
                key={tr.value}
                onClick={() => setHours(tr.value)}
                style={{
                  padding: '6px 14px', fontSize: 12, fontWeight: 500,
                  background: hours === tr.value ? T.primary : T.gray50,
                  color: hours === tr.value ? T.white : T.gray600,
                  border: `1px solid ${hours === tr.value ? T.primaryBorder : T.gray200}`,
                  borderRadius: T.radiusSm, cursor: 'pointer',
                }}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </div>

        {/* Category filter */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', paddingBottom: 14 }}>
          <button
            onClick={() => setCategory('')}
            style={{
              padding: '4px 12px', fontSize: 11, fontWeight: 500,
              background: !category ? T.primary : T.gray50,
              color: !category ? T.white : T.gray600,
              border: `1px solid ${!category ? T.primaryBorder : T.gray200}`,
              borderRadius: 20, cursor: 'pointer',
            }}
          >
            全部
          </button>
          {CATEGORIES.map(c => (
            <button
              key={c}
              onClick={() => setCategory(c === category ? '' : c)}
              style={{
                padding: '4px 12px', fontSize: 11, fontWeight: 500,
                background: category === c ? T.primary : T.gray50,
                color: category === c ? T.white : T.gray600,
                border: `1px solid ${category === c ? T.primaryBorder : T.gray200}`,
                borderRadius: 20, cursor: 'pointer',
              }}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: '20px 28px' }}>
        {/* Stats bar */}
        <div style={{
          display: 'flex', gap: 16, marginBottom: 16,
          fontSize: 12, color: T.gray500,
        }}>
          <span>共 <b style={{ color: T.gray700 }}>{total}</b> 条低粉爆文</span>
          {total > 0 && (
            <span>当前 <b style={{ color: T.gray700 }}>{startItem}-{endItem}</b> 条</span>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: 'center', padding: 60, color: T.gray400, fontSize: 14 }}>
            加载中...
          </div>
        )}

        {/* Empty */}
        {!loading && items.length === 0 && (
          <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
            暂无低粉爆文数据
          </div>
        )}

        {/* List */}
        {!loading && items.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map((item) => {
              const lfvScore = getLfvScore(item);
              const sourceWeight = getSourceWeight(item);
              const obscureFactor = getObscureFactor(item);
              const isFav = favorites.has(item.id);
              const isExpanded = selectedAnalysis && (selectedAnalysis as any)._content_id === item.id;

              return (
                <div
                  key={item.id}
                  style={{
                    background: T.white,
                    borderRadius: T.radiusSm,
                    border: `1px solid ${isExpanded ? T.primaryBorder : T.gray100}`,
                    overflow: 'hidden',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {/* Card header */}
                  <div
                    style={{ padding: '14px 18px', cursor: 'pointer' }}
                    onClick={() => setSelectedAnalysis(
                      isExpanded ? null : ({ ...(item as any).analysis, _content_id: item.id } as any)
                    )}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                      {/* Left: LFV badge + title */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          {/* LFV score badge */}
                          <div style={{
                            background: lfvScore >= 40 ? '#FF6B35' : lfvScore >= 25 ? '#F59E0B' : T.gray200,
                            color: T.white, fontSize: 11, fontWeight: 700,
                            padding: '2px 8px', borderRadius: 4, flexShrink: 0,
                          }}>
                            LFV {lfvScore.toFixed(1)}
                          </div>
                          {/* Category */}
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: '2px 8px',
                            background: T.gray100, color: T.gray600,
                            borderRadius: 4, flexShrink: 0,
                          }}>
                            {item.category}
                          </span>
                          {/* Title */}
                          <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.title}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: T.gray400, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                          <span>{item.source_name}</span>
                          {item.published_at && (
                            <span>{new Date(item.published_at).toLocaleDateString('zh-CN')}</span>
                          )}
                          <span style={{ color: T.gray300 }}>源权威: {sourceWeight.toFixed(0)}</span>
                          <span style={{ color: sourceWeight <= 30 ? '#10B981' : T.gray400 }}>
                            隐蔽指数: ×{obscureFactor.toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Right: actions */}
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
                        {item.url && (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={e => e.stopPropagation()}
                            style={{
                              fontSize: 12, color: T.gray400, textDecoration: 'none',
                              padding: '4px 8px', borderRadius: 4, border: `1px solid ${T.gray200}`,
                            }}
                            title="查看原文"
                          >
                            ↗
                          </a>
                        )}
                        <button
                          onClick={e => { e.stopPropagation(); void toggleFavorite(item.id); }}
                          style={{
                            fontSize: 12, padding: '4px 8px',
                            background: isFav ? '#FEF3C7' : T.gray50,
                            color: isFav ? '#D97706' : T.gray400,
                            border: `1px solid ${isFav ? '#FDE68A' : T.gray200}`,
                            borderRadius: 4, cursor: 'pointer',
                          }}
                          title={isFav ? '取消收藏' : '收藏'}
                        >
                          ★
                        </button>
                        <span style={{
                          fontSize: 12, color: T.gray300,
                          transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                          transition: 'transform 0.15s',
                        }}>
                          ▼
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Expanded analysis */}
                  {isExpanded && (
                    <div style={{ borderTop: `1px solid ${T.gray100}`, padding: '16px 18px', background: T.gray50 }}>
                      <AnalysisPanel
                        analysis={selectedAnalysis as ContentAnalysis}
                        onClose={() => setSelectedAnalysis(null)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {!loading && totalPages > 1 && (
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginTop: 24, padding: '0 4px',
          }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{
                padding: '8px 16px', fontSize: 13,
                background: page === 1 ? T.gray50 : T.white,
                color: page === 1 ? T.gray300 : T.gray700,
                border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
                cursor: page === 1 ? 'not-allowed' : 'pointer',
              }}
            >
              ← 上一页
            </button>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (page <= 3) {
                  pageNum = i + 1;
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = page - 2 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    style={{
                      width: 32, height: 32, fontSize: 13, fontWeight: page === pageNum ? 700 : 400,
                      background: page === pageNum ? T.primary : T.white,
                      color: page === pageNum ? T.white : T.gray600,
                      border: `1px solid ${page === pageNum ? T.primaryBorder : T.gray200}`,
                      borderRadius: T.radiusSm, cursor: 'pointer',
                    }}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{
                padding: '8px 16px', fontSize: 13,
                background: page === totalPages ? T.gray50 : T.white,
                color: page === totalPages ? T.gray300 : T.gray700,
                border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
                cursor: page === totalPages ? 'not-allowed' : 'pointer',
              }}
            >
              下一页 →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
