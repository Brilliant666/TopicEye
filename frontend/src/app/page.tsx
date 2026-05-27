'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Ban,
  Check,
  ChevronDown,
  Clock3,
  Eye,
  Flame,
  Star,
  ThumbsDown,
  ThumbsUp,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T, SOURCE_TYPE_COLOR_MAP } from '@/lib/design-tokens';
import { useAppContext } from '@/components/ClientLayout';
import Header from '@/components/Header';
import CategoryChip from '@/components/CategoryChip';
import { contentsApi, feedbackApi } from '@/lib/api';
import type { FeedbackType } from '@/lib/api';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';
import { getRecommendLevel } from '@/types';
import ContentAnalysisPanel from '@/components/ContentAnalysisPanel';

// ── Helpers ──

/** Parse a datetime string from backend (UTC, no 'Z' suffix) into a correct Date */
function parseUTC(s: string): Date {
  const normalized = s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s) ? s : s + 'Z';
  return new Date(normalized);
}

function formatTime(dateStr: string): string {
  try {
    const d = parseUTC(dateStr);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  } catch {
    return '--:--';
  }
}

function timeAgo(dateStr: string): string {
  try {
    const now = Date.now();
    const then = parseUTC(dateStr).getTime();
    const diffSec = Math.floor((now - then) / 1000);
    if (diffSec < 60) return '刚刚';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} 天前`;
    return parseUTC(dateStr).toLocaleDateString('zh-CN');
  } catch {
    return '';
  }
}

function isToday(dateStr: string): boolean {
  try {
    const d = parseUTC(dateStr);
    const now = new Date();
    return (
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    );
  } catch {
    return false;
  }
}

// ── Page Component ──

export default function HomePage() {
  const { favorites, toggleFavorite, refreshCounts } = useAppContext();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('全部');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTimeRange, setActiveTimeRange] = useState('48h');
  const [activeSourceType, setActiveSourceType] = useState('全部');
  const [selectedAnalysis, setSelectedAnalysis] = useState<ContentAnalysis | null>(null);

  // Fetch data
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await contentsApi.list({
          page_size: 50,
          hours: activeTimeRange === '全部' ? undefined : parseInt(activeTimeRange),
          source_type: activeSourceType === '全部' ? undefined : activeSourceType,
        });
        if (!cancelled) {
          setItems(res.items || []);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '获取内容失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeTimeRange, activeSourceType]);

  const handleIgnore = useCallback(async (id: number) => {
    try {
      await contentsApi.ignore(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
      refreshCounts?.();
    } catch (err) {
      console.error('Ignore failed:', err);
    }
  }, [refreshCounts]);

  // Dynamic categories derived from data
  const categories = useMemo(() => {
    const set = new Set<string>();
    items.forEach((item) => {
      if (item.category) set.add(item.category);
    });
    return ['全部', ...Array.from(set).sort()];
  }, [items]);

  // Filtered + sorted list
  const filtered = useMemo(() => {
    const result = items.filter((item) => {
      // Category filter
      if (activeCategory !== '全部' && item.category !== activeCategory) return false;
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        if (!item.title.toLowerCase().includes(q)) return false;
      }
      return true;
    });
    // Sort by published_at descending
    result.sort((a, b) => {
      const ta = new Date(a.published_at).getTime() || 0;
      const tb = new Date(b.published_at).getTime() || 0;
      return tb - ta;
    });
    return result;
  }, [items, activeCategory, searchQuery]);

  const grouped = useMemo(() => {
    const groups: Array<{ level: RecommendLevel; title: string; items: ContentItem[] }> = [
      { level: '强烈建议写', title: '主编推荐', items: [] },
      { level: '值得观察', title: '值得观察', items: [] },
      { level: '适合深挖', title: '适合深挖', items: [] },
      { level: '适合蹭热点', title: '热点观察', items: [] },
      { level: '不建议追', title: '低优先级', items: [] },
    ];
    const fallback = groups[1];
    filtered.forEach((item) => {
      const level = item.analysis ? getRecommendLevel(item.analysis) : '值得观察';
      (groups.find((g) => g.level === level) || fallback).items.push(item);
    });
    return groups.filter((g) => g.items.length > 0);
  }, [filtered]);

  // Stats
  const totalCount = items.length;
  const todayCount = useMemo(() => items.filter((i) => isToday(i.published_at)).length, [items]);

  // Today's date
  const today = new Date();
  const dateStr = `${today.getFullYear()} 年 ${today.getMonth() + 1} 月 ${today.getDate()} 日`;

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <Header
        title="今日选题"
        date={dateStr}
        stats={[
          { label: '总内容', value: totalCount, color: T.primary },
          { label: '今日新增', value: todayCount, color: T.teal },
        ]}
      />

      {/* Search bar */}
      <div style={{ maxWidth: 820, marginBottom: 16 }}>
        <input
          type="text"
          placeholder="搜索标题..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '10px 16px',
            fontSize: 13,
            border: `1px solid ${T.gray200}`,
            borderRadius: T.radius,
            outline: 'none',
            background: T.white,
            color: T.gray900,
            transition: 'border-color 0.2s',
            boxSizing: 'border-box',
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = T.primary)}
          onBlur={(e) => (e.currentTarget.style.borderColor = T.gray200)}
        />
      </div>

      {/* Filter row: time range + source type */}
      <div style={{ maxWidth: 820, marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {/* Time range */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: T.gray500, fontWeight: 500 }}>时间</span>
            {['24h', '48h', '7d', '全部'].map((range) => (
              <button
                key={range}
                onClick={() => setActiveTimeRange(range)}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  fontWeight: activeTimeRange === range ? 600 : 400,
                  color: activeTimeRange === range ? T.primary : T.gray500,
                  background: activeTimeRange === range ? T.primaryLight : T.gray50,
                  border: 'none',
                  borderRadius: T.radiusXs,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                {range === '全部' ? '全部' : range === '24h' ? '24小时' : range === '48h' ? '48小时' : '近7天'}
              </button>
            ))}
          </div>
          {/* Divider */}
          <div style={{ width: 1, height: 20, background: T.gray200 }} />
          {/* Source type */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: T.gray500, fontWeight: 500 }}>来源</span>
            {['全部', 'RSS', 'RSSHub', '公众号', '网站', 'Reddit', 'Zhihu'].map((type) => (
              <button
                key={type}
                onClick={() => setActiveSourceType(type)}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  fontWeight: activeSourceType === type ? 600 : 400,
                  color: activeSourceType === type ? T.primary : T.gray500,
                  background: activeSourceType === type ? T.primaryLight : T.gray50,
                  border: 'none',
                  borderRadius: T.radiusXs,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filters - Category */}
      <div style={{ maxWidth: 820, marginBottom: 28 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {categories.map((c) => (
            <CategoryChip
              key={c}
              name={c}
              active={activeCategory === c}
              onClick={() => setActiveCategory(c)}
            />
          ))}
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div
          style={{
            maxWidth: 820,
            padding: '16px 20px',
            background: T.redLight,
            color: T.red,
            borderRadius: T.radius,
            fontSize: 14,
            marginBottom: 20,
            border: `1px solid ${T.red}`,
          }}
        >
          加载失败：{error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={{ maxWidth: 820, textAlign: 'center', padding: 60 }}>
          <Spinner />
          <div style={{ marginTop: 12, color: T.gray400, fontSize: 13 }}>加载中...</div>
        </div>
      )}

      {/* Editorial content flow */}
      {!loading && !error && (
        <div style={{ maxWidth: 820, paddingBottom: 60 }}>
          {grouped.map((group) => (
            <section key={group.level} style={{ marginBottom: 28 }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingBottom: 10,
                marginBottom: 12,
                borderBottom: `1px solid ${T.gray200}`,
              }}>
                <h2 style={{ fontSize: 15, fontWeight: 800, color: T.gray900 }}>
                  {group.title}
                </h2>
                <span style={{ fontSize: 12, color: T.gray400, fontFamily: T.mono }}>
                  {group.items.length}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {group.items.map((item) => (
                  <EditorialItem
                    key={item.id}
                    item={item}
                    isFav={favorites.has(item.id)}
                    onToggleFav={toggleFavorite}
                    onIgnore={handleIgnore}
                    time={formatTime(item.published_at)}
                    timeLabel={timeAgo(item.published_at)}
                    onShowAnalysis={(a) => setSelectedAnalysis(a)}
                  />
                ))}
              </div>
            </section>
          ))}
          {filtered.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60, color: T.gray400, fontSize: 14 }}>
              当前筛选条件下没有内容
            </div>
          )}
        </div>
      )}

      {/* Analysis panel overlay */}
      {selectedAnalysis && (
        <>
          <div
            onClick={() => setSelectedAnalysis(null)}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.2)',
              zIndex: 999,
            }}
          />
          <ContentAnalysisPanel
            analysis={selectedAnalysis}
            onClose={() => setSelectedAnalysis(null)}
          />
        </>
      )}
    </div>
  );
}

// ── Spinner ──

function Spinner() {
  return (
    <div
      style={{
        display: 'inline-block',
        width: 28,
        height: 28,
        border: `3px solid ${T.gray200}`,
        borderTopColor: T.primary,
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}
    />
  );
}

// ── Editorial Item Component ──

function EditorialItem({
  item,
  isFav,
  onToggleFav,
  onIgnore,
  time,
  timeLabel,
  onShowAnalysis,
}: {
  item: ContentItem;
  isFav: boolean;
  onToggleFav: (id: number) => void;
  onIgnore: (id: number) => void;
  time: string;
  timeLabel: string;
  onShowAnalysis: (analysis: ContentAnalysis) => void;
}) {
  const [hovered, setHovered] = useState(false);

  const handleCardClick = useCallback(() => {
    if (item.analysis) {
      onShowAnalysis(item.analysis);
    } else if (item.url) {
      window.open(item.url, '_blank', 'noopener,noreferrer');
    }
  }, [item.analysis, item.url, onShowAnalysis]);

  const recommendation = item.analysis?.recommendation || item.analysis?.recommended_reason || item.summary;

  return (
      <div
        onClick={handleCardClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          flex: 1,
          minWidth: 0,
          overflow: 'hidden',
          background: T.white,
          borderRadius: T.radius,
          padding: '18px 22px',
          cursor: item.url ? 'pointer' : 'default',
          transition: 'all 0.2s ease',
          boxShadow: hovered
            ? '0 6px 20px rgba(0,0,0,0.07)'
            : '0 1px 3px rgba(0,0,0,0.04)',
          border: `1px solid ${hovered ? T.primaryBorder : T.gray100}`,
        }}
      >
        {/* Card header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 8,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <span style={{ fontSize: 12, color: T.gray600, fontWeight: 600 }}>
              {item.source_name}
            </span>
            <span style={{ fontSize: 12, color: T.gray300 }}>/</span>
            <span style={{ fontSize: 12, color: T.gray400 }}>{timeLabel || time}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {item.category && (
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: T.gray600,
                  background: T.gray100,
                  padding: '2px 8px',
                  borderRadius: 4,
                }}
              >
                {item.category}
              </span>
            )}
          </div>
        </div>

        {/* Title */}
        <h3
          style={{
            fontSize: 16,
            fontWeight: 600,
            lineHeight: 1.55,
            color: T.gray900,
            marginBottom: 8,
          }}
        >
          {item.title}
        </h3>

        {/* Editorial reason */}
        {recommendation && (
          <div
            style={{
              borderLeft: `3px solid ${T.primary}`,
              padding: '6px 0 6px 12px',
              fontSize: 13,
              lineHeight: 1.7,
              color: T.gray600,
              marginBottom: 12,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            推荐理由：{recommendation}
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              flexWrap: 'wrap',
            }}
          >
            {item.analysis && hovered && (
              <>
                <CurationScoreBadge score={item.analysis.adjusted_curation_score ?? item.analysis.curation_score} />
                <ScoreBadge label="创作" score={item.analysis.creator_score} color={T.primary} />
                <ScoreBadge label="爆文" score={item.analysis.viral_score} color={T.gray600} />
                <ScoreBadge label="质量" score={item.analysis.quality_score} color={T.gray600} />
                <RecommendBadge level={getRecommendLevel(item.analysis)} />
              </>
            )}
            {hovered && item.tags && item.tags.length > 0
              ? item.tags.slice(0, 5).map((tag) => (
                  <span
                    key={tag}
                    style={{
                      fontSize: 11,
                      color: T.gray500,
                      fontWeight: 500,
                      background: T.gray100,
                      padding: '2px 8px',
                      borderRadius: 4,
                    }}
                  >
                    #{tag}
                  </span>
                ))
              : null}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {item.analysis && hovered && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onShowAnalysis(item.analysis as ContentAnalysis);
                }}
                style={{
                  border: `1px solid ${T.gray200}`,
                  background: T.white,
                  color: T.gray500,
                  borderRadius: T.radiusXs,
                  padding: '4px 8px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 12,
                }}
              >
                <Eye size={13} strokeWidth={2} />
                分析
              </button>
            )}
            {/* Feedback buttons */}
            <FeedbackButtons contentId={item.id} />
            {/* Favorite */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleFav(item.id);
              }}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 2,
                color: isFav ? T.primary : T.gray300,
                transition: 'color 0.15s',
                display: 'inline-flex',
                alignItems: 'center',
              }}
              title={isFav ? '取消收藏' : '收藏'}
            >
              <Star size={16} strokeWidth={2} fill={isFav ? T.primary : 'none'} />
            </button>
            {/* Ignore */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onIgnore(item.id);
              }}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 2,
                color: T.gray300,
                transition: 'color 0.15s',
                display: 'inline-flex',
                alignItems: 'center',
              }}
              title="不感兴趣"
              onMouseEnter={(e) => (e.currentTarget.style.color = T.gray500)}
              onMouseLeave={(e) => (e.currentTarget.style.color = T.gray300)}
            >
              <X size={15} strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>
  );
}

// ── Score Badge ──

function ScoreBadge({ label, score, color }: { label: string; score: number; color: string }) {
  const scoreColor = score >= 75 ? color : score >= 50 ? T.gray600 : T.gray400;
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        color: scoreColor,
        background: `${color}10`,
        padding: '2px 6px',
        borderRadius: 4,
        fontFamily: T.mono,
      }}
    >
      {label}{Math.round(score)}
    </span>
  );
}

// ── Recommend Badge ──

function RecommendBadge({ level }: { level: RecommendLevel }) {
  const colorMap: Record<RecommendLevel, { bg: string; color: string }> = {
    '强烈建议写': { bg: '#dcfce7', color: '#16a34a' },
    '值得观察': { bg: '#dbeafe', color: '#2563eb' },
    '适合深挖': { bg: '#fef3c7', color: '#d97706' },
    '适合蹭热点': { bg: '#fee2e2', color: '#dc2626' },
    '不建议追': { bg: '#f3f4f6', color: '#9ca3af' },
  };
  const { bg, color } = colorMap[level] || { bg: '#f3f4f6', color: '#9ca3af' };
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        color,
        background: bg,
        padding: '2px 8px',
        borderRadius: 4,
      }}
    >
      {level}
    </span>
  );
}

// ── Curation Score Badge ──

function CurationScoreBadge({ score }: { score: number | null | undefined }) {
  if (score == null || score === 0) return null;
  const rounded = Math.round(score);
  let color: string = T.gray400;
  let bg: string = T.gray100;
  if (rounded >= 85) { color = '#16a34a'; bg = '#dcfce7'; }
  else if (rounded >= 70) { color = '#2563eb'; bg = '#dbeafe'; }
  else if (rounded >= 55) { color = '#d97706'; bg = '#fef3c7'; }
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 700,
        color,
        background: bg,
        padding: '2px 7px',
        borderRadius: 4,
        fontFamily: T.mono,
        letterSpacing: '-0.3px',
      }}
    >
      {rounded}
    </span>
  );
}

// ── Feedback Buttons ──

const FEEDBACK_OPTIONS: { type: FeedbackType; icon: LucideIcon; label: string; color: string }[] = [
  { type: 'great_pick', icon: Flame, label: '精选好文', color: '#16a34a' },
  { type: 'like', icon: ThumbsUp, label: '有价值', color: '#2563eb' },
  { type: 'dislike', icon: ThumbsDown, label: '不感兴趣', color: '#dc2626' },
  { type: 'not_relevant', icon: Ban, label: '不相关', color: '#9ca3af' },
  { type: 'outdated', icon: Clock3, label: '过时了', color: '#d97706' },
];

function FeedbackButtons({ contentId }: { contentId: number }) {
  const [activeFeedback, setActiveFeedback] = useState<FeedbackType | null>(null);
  const [showMore, setShowMore] = useState(false);

  const handleFeedback = async (type: FeedbackType) => {
    if (activeFeedback === type) return; // already submitted
    try {
      await feedbackApi.submit(contentId, type);
      setActiveFeedback(type);
    } catch (err: unknown) {
      // 409 = duplicate, that's fine
      const msg = err instanceof Error ? err.message : String(err);
      if (!msg?.includes('409') && !msg?.includes('Conflict')) {
        console.error('Feedback failed:', err);
      }
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2, position: 'relative' }}>
      {/* Quick feedback: thumbs up/down */}
      {FEEDBACK_OPTIONS.slice(0, 2).map(({ type, icon: Icon, label, color }) => (
        <button
          key={type}
          onClick={(e) => {
            e.stopPropagation();
            handleFeedback(type);
          }}
          title={label}
          style={{
            background: activeFeedback === type ? `${color}15` : 'none',
            border: 'none',
            cursor: activeFeedback === type ? 'default' : 'pointer',
            padding: '2px 4px',
            borderRadius: 4,
            opacity: activeFeedback && activeFeedback !== type ? 0.3 : 1,
            transition: 'all 0.15s',
            color: activeFeedback === type ? color : T.gray400,
            display: 'inline-flex',
            alignItems: 'center',
          }}
        >
          <Icon size={13} strokeWidth={2.2} />
        </button>
      ))}
      
      {/* More feedback options dropdown */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowMore(!showMore);
          }}
          style={{
            background: showMore ? T.gray100 : 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 6px',
            borderRadius: 4,
            color: T.gray400,
            transition: 'all 0.15s',
            display: 'inline-flex',
            alignItems: 'center',
          }}
          title="更多反馈"
        >
          <ChevronDown size={13} strokeWidth={2.2} />
        </button>
        {showMore && (
          <>
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'absolute',
                right: 0,
                top: '100%',
                marginTop: 4,
                background: T.white,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radiusSm,
                boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                padding: 4,
                zIndex: 100,
                minWidth: 120,
              }}
            >
              {FEEDBACK_OPTIONS.map(({ type, icon: Icon, label, color }) => (
                <button
                  key={type}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleFeedback(type);
                    setShowMore(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '6px 10px',
                    background: activeFeedback === type ? `${color}10` : 'none',
                    border: 'none',
                    borderRadius: 4,
                    cursor: activeFeedback === type ? 'default' : 'pointer',
                    fontSize: 12,
                    color: activeFeedback === type ? color : T.gray600,
                    fontWeight: activeFeedback === type ? 600 : 400,
                    textAlign: 'left' as const,
                  }}
                >
                  <Icon size={13} strokeWidth={2.2} />
                  <span>{label}</span>
                  {activeFeedback === type && <Check size={12} strokeWidth={2.4} style={{ marginLeft: 'auto' }} />}
                </button>
              ))}
            </div>
            {/* Click outside to close */}
            <div
              onClick={() => setShowMore(false)}
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 99,
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}
