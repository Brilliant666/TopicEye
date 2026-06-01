'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, RefreshCw, Star } from 'lucide-react';
import { contentsApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import { Badge, Panel, cx } from '@/components/ui';
import ContentAnalysisPanel from '@/components/ContentAnalysisPanel';
import type { ContentItem, ContentAnalysis } from '@/types';
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
  const { favoritePendingIds, toggleFavorite } = useAppContext();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAnalysis, setSelectedAnalysis] = useState<ContentAnalysis | null>(null);

  const fetchFavorites = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await contentsApi.listFavorites({ page_size: 100 });
      setItems(res.items || []);
      setTotal(res.total ?? res.items?.length ?? 0);
    } catch (err) {
      console.error('Failed to fetch favorites:', err);
      setError(err instanceof Error ? err.message : '收藏夹加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchFavorites();
  }, [fetchFavorites]);

  const handleUnfav = async (id: number) => {
    setError(null);
    try {
      const isFavorited = await toggleFavorite(id, { throwOnError: true });
      if (!isFavorited) {
        setItems((prev) => prev.filter((item) => item.id !== id));
        setTotal((prev) => Math.max(0, prev - 1));
      } else {
        setError('取消收藏未生效，请稍后重试');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消收藏失败');
    }
  };

  return (
    <div className="fade-in h-full overflow-y-auto px-10 py-8">
      <div className="mb-7">
        <h1 className="mb-1.5 text-[26px] font-bold text-gray-900">收藏夹</h1>
        <p className="text-[13px] text-gray-400">
          已收藏 <b className="font-mono text-primary">{total}</b> 条内容
        </p>
      </div>

      {error && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-sm border border-red/20 bg-red-light px-4 py-3 text-[13px] text-red">
          <div className="flex min-w-0 items-center gap-2">
            <AlertCircle size={15} className="shrink-0" />
            <span className="break-words">{error}</span>
          </div>
          <button
            type="button"
            onClick={() => void fetchFavorites()}
            className="inline-flex shrink-0 items-center gap-1 rounded-xs border border-red/20 bg-white px-2.5 py-1 text-[11px] font-bold text-red"
          >
            <RefreshCw size={12} />
            重试
          </button>
        </div>
      )}

      {loading ? (
        <div className="p-20 text-center text-sm text-gray-400">
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="p-20 text-center text-sm text-gray-400">
          <Star size={38} className="mx-auto mb-4 text-gray-300 opacity-70" strokeWidth={1.8} />
          <div>还没有收藏任何内容</div>
          <div className="mt-1 text-xs">在今日选题中点击星标即可收藏</div>
        </div>
      ) : (
        <div className="flex flex-col gap-4 pb-10">
          {items.map((item) => {
            const analysis = item.analysis as ContentAnalysis | null;
            const level = analysis ? getRecommendLevel(analysis) : null;
            return (
              <Panel
                key={item.id}
                onClick={() => analysis && setSelectedAnalysis(analysis)}
                className={cx('px-6 py-5 transition hover:shadow-md', analysis ? 'cursor-pointer' : 'cursor-default')}
              >
                {/* Header */}
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="mb-1.5 flex items-center gap-2 text-[11px] text-gray-400">
                      <span>{item.source_name}</span>
                      <span className="text-gray-300">·</span>
                      <span>{item.category}</span>
                      <span className="text-gray-300">·</span>
                      <span>{timeAgo(item.published_at || item.crawled_at)}</span>
                    </div>
                    <h3 className="text-[15px] font-semibold leading-6 text-gray-900">
                      {item.title}
                    </h3>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleUnfav(item.id); }}
                    disabled={favoritePendingIds.has(item.id)}
                    className="inline-flex items-center border-0 bg-transparent px-2 py-1 text-primary disabled:cursor-wait disabled:opacity-50"
                    title="取消收藏"
                  >
                    <Star size={18} strokeWidth={2} fill="#FF6B35" />
                  </button>
                </div>

                {/* Scores */}
                {analysis && (
                  <div className="flex flex-wrap items-center gap-2.5">
                    <ScoreBadge label="创作" value={analysis.creator_score} colorClass="text-primary" />
                    <ScoreBadge label="爆文" value={analysis.viral_score} colorClass="text-amber" />
                    <ScoreBadge label="质量" value={analysis.quality_score} colorClass="text-teal" />
                    {level && <RecommendBadge level={level} />}
                  </div>
                )}

                {/* Summary */}
                {analysis?.summary && (
                  <p className="mt-2 text-[13px] leading-6 text-gray-500">
                    {analysis.summary}
                  </p>
                )}
              </Panel>
            );
          })}
        </div>
      )}

      {/* Analysis panel overlay */}
      {selectedAnalysis && (
        <>
          <div
            onClick={() => setSelectedAnalysis(null)}
            className="fixed inset-0 z-[999] bg-black/20"
          />
          <ContentAnalysisPanel analysis={selectedAnalysis} onClose={() => setSelectedAnalysis(null)} />
        </>
      )}
    </div>
  );
}

// ─── Score Badge ───

function ScoreBadge({ label, value, colorClass }: { label: string; value: number; colorClass: string }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-[11px] text-gray-500">{label}</span>
      <span className={cx('text-xs font-bold', colorClass)}>{Math.round(value)}</span>
    </div>
  );
}

function RecommendBadge({ level }: { level: string }) {
  const tone = level === '强烈建议写' ? 'primary' : level === '值得观察' ? 'teal' : level === '适合深挖' ? 'purple' : level === '适合蹭热点' ? 'amber' : 'neutral';
  return <Badge tone={tone} className="rounded px-2 py-0.5 text-[11px] font-medium">{level}</Badge>;
}
