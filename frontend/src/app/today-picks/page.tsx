'use client';

import React, { useState, useEffect, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { T, CATEGORIES, RECOMMEND_LEVELS, LEVEL_CONFIG } from '@/lib/design-tokens';
import { contentsApi, creationApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import CategoryChip from '@/components/CategoryChip';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const hours = Math.floor(diffMs / 3600000);
  if (hours < 1) return '刚刚';
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

const TAG_COLORS: Record<string, string> = {
  '模型': '#8B5CF6', '产品': '#3B82F6', '行业': '#10B981',
  '论文': '#6366F1', '技巧': '#F59E0B', '开源': '#EF4444',
  '工具': '#EC4899', '趋势': '#14B8A6', '大佬': '#F97316',
  '智能体': '#06B6D4', '具身智能': '#84CC16', '编码': '#A855F7',
};
function getTagColor(tag: string): string { return TAG_COLORS[tag] || T.gray400; }

function getRecommendLevelLabel(analysis: ContentAnalysis): string {
  const { creator_score, hot_score, quality_score, freshness_score, risk_score } = analysis;
  if (creator_score >= 85 && risk_score <= 40) return '强烈建议写';
  if (creator_score >= 70 && hot_score >= 70) return '值得观察';
  if (quality_score >= 85 && freshness_score < 50) return '适合深挖';
  if (hot_score >= 80 && risk_score > 40) return '适合蹭热点';
  if (creator_score < 50) return '不建议追';
  return '值得观察';
}

interface TopicInfo {
  id: number;
  name: string;
  summary: string | null;
  keywords: string[] | null;
  best_score: number;
}

const TIME_RANGES = [
  { value: '', label: '全部时间' },
  { value: '24h', label: '24小时' },
  { value: '48h', label: '48小时' },
  { value: '7d', label: '7天' },
] as const;

// Wrapper with Suspense for useSearchParams
export default function TodayPicksPageWrapper() {
  return (
    <Suspense fallback={<div style={{ textAlign: 'center', padding: 80, color: '#9CA3AF', fontSize: 14 }}>加载中...</div>}>
      <TodayPicksPage />
    </Suspense>
  );
}

function TodayPicksPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { favorites, toggleFavorite } = useAppContext();

  // Filter state initialized from URL params
  const [selectedCategory, setSelectedCategory] = useState<string>(searchParams.get('category') || '');
  const [selectedLevel, setSelectedLevel] = useState<string>(searchParams.get('level') || '');
  const [selectedTimeRange, setSelectedTimeRange] = useState<string>(searchParams.get('time_range') || '');

  const [items, setItems] = useState<ContentItem[]>([]);
  const [topics, setTopics] = useState<TopicInfo[]>([]);
  const [dupCount, setDupCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedAnalysis, setSelectedAnalysis] = useState<(ContentAnalysis & { _content_id?: number }) | null>(null);
  const [groupByTopic, setGroupByTopic] = useState(true);
  const [expandedTopics, setExpandedTopics] = useState<Set<number>>(new Set());

  // Sync filters to URL
  const updateURL = useCallback((cat: string, level: string, tr: string) => {
    const params = new URLSearchParams();
    if (cat) params.set('category', cat);
    if (level) params.set('level', level);
    if (tr) params.set('time_range', tr);
    const qs = params.toString();
    router.replace(`/today-picks${qs ? '?' + qs : ''}`, { scroll: false });
  }, [router]);

  const setCategory = (cat: string) => {
    setSelectedCategory(cat);
    updateURL(cat, selectedLevel, selectedTimeRange);
  };
  const setLevel = (level: string) => {
    setSelectedLevel(level);
    updateURL(selectedCategory, level, selectedTimeRange);
  };
  const setTimeRange = (tr: string) => {
    setSelectedTimeRange(tr);
    updateURL(selectedCategory, selectedLevel, tr);
  };

  const fetchPicks = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, string> = {};
      if (selectedCategory) params.category = selectedCategory;
      if (selectedTimeRange) params.time_range = selectedTimeRange;
      const res = await contentsApi.todayPicks(params);
      const data = res as any;
      setItems(data.items || []);
      setTopics(data.topics || []);
      setDupCount(data.duplicates_hidden || 0);
    } catch (err) {
      console.error('Failed to fetch today picks:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, selectedTimeRange]);

  useEffect(() => { fetchPicks(); }, [fetchPicks]);

  const handleFav = async (id: number) => { await toggleFavorite(id); };
  const toggleTopic = (id: number) => {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // Client-side recommend level filter
  const filteredItems = useMemo(() => {
    if (!selectedLevel) return items;
    return items.filter(item => {
      const analysis = (item.analysis || (item as any).analyses?.[0]) as ContentAnalysis | null;
      if (!analysis) return false;
      const level = getRecommendLevelLabel(analysis);
      return level === selectedLevel;
    });
  }, [items, selectedLevel]);

  // Group items by topic_id
  const topicMap = new Map<number | null, ContentItem[]>();
  for (const item of filteredItems) {
    const tid = (item as any).topic_id || null;
    if (!topicMap.has(tid)) topicMap.set(tid, []);
    topicMap.get(tid)!.push(item);
  }

  // Topic info lookup
  const topicInfoMap = new Map(topics.map(t => [t.id, t]));

  // Ordered: topics with items first (by best_score desc), then standalone items
  const sortedTopics = topics
    .filter(t => topicMap.has(t.id) && (topicMap.get(t.id)?.length || 0) > 0)
    .sort((a, b) => b.best_score - a.best_score);

  const standaloneItems = topicMap.get(null) || [];

  // Count active filters
  const activeFilterCount = [selectedCategory, selectedLevel, selectedTimeRange].filter(Boolean).length;

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>当日精选</h1>
          <span style={{
            fontSize: 10, fontWeight: 700, color: T.white,
            background: 'linear-gradient(135deg, #FF6B35, #FF8F65)',
            padding: '3px 10px', borderRadius: 20,
          }}>
            AI PICKED
          </span>
          {/* Toggle group mode */}
          <button
            onClick={() => setGroupByTopic(!groupByTopic)}
            style={{
              marginLeft: 'auto', fontSize: 11, padding: '4px 12px', borderRadius: 6,
              border: `1px solid ${groupByTopic ? T.primary : T.gray200}`,
              background: groupByTopic ? `${T.primary}10` : T.white,
              color: groupByTopic ? T.primary : T.gray500,
              cursor: 'pointer', fontWeight: 600,
            }}
          >
            {groupByTopic ? '📊 话题分组' : '📋 平铺列表'}
          </button>
        </div>
        <p style={{ fontSize: 13, color: T.gray400 }}>
          精选分 ≥ 60 入选 · 去重后 <b style={{ color: T.primary, fontFamily: T.mono }}>{filteredItems.length}</b> 条
          {dupCount > 0 && <span style={{ color: T.gray400 }}>（隐藏 {dupCount} 条重复）</span>}
          {sortedTopics.length > 0 && groupByTopic && <span> · {sortedTopics.length} 个话题</span>}
        </p>
      </div>

      {/* ── Filter Bar ── */}
      <div style={{
        background: T.white, borderRadius: T.radius,
        border: `1px solid ${T.gray100}`, padding: '14px 18px',
        marginBottom: 20,
      }}>
        {/* Row 1: Category chips */}
        <div style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginRight: 8, verticalAlign: 'middle' }}>
            📂 分类
          </span>
          <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', verticalAlign: 'middle' }}>
            {(CATEGORIES as readonly string[]).map((cat) => (
              <CategoryChip
                key={cat}
                name={cat}
                active={selectedCategory === cat || (!selectedCategory && cat === '全部')}
                onClick={() => setCategory(cat === '全部' ? '' : cat)}
              />
            ))}
          </div>
        </div>

        {/* Row 2: Recommend level + Time range */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500 }}>🎯 等级</span>
            {RECOMMEND_LEVELS.map((level) => {
              const cfg = LEVEL_CONFIG[level];
              const isActive = selectedLevel === level;
              return (
                <button
                  key={level}
                  onClick={() => setLevel(isActive ? '' : level)}
                  style={{
                    fontSize: 11, fontWeight: isActive ? 600 : 400,
                    padding: '3px 10px', borderRadius: 12,
                    border: isActive ? 'none' : `1px solid ${T.gray200}`,
                    background: isActive ? cfg.bg : T.white,
                    color: isActive ? cfg.color : T.gray600,
                    cursor: 'pointer', transition: 'all 0.15s',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {level}
                </button>
              );
            })}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500 }}>🕐 时间</span>
            {TIME_RANGES.map((tr) => {
              const isActive = selectedTimeRange === tr.value;
              return (
                <button
                  key={tr.value}
                  onClick={() => setTimeRange(isActive ? '' : tr.value)}
                  style={{
                    fontSize: 11, fontWeight: isActive ? 600 : 400,
                    padding: '3px 10px', borderRadius: 12,
                    border: isActive ? 'none' : `1px solid ${T.gray200}`,
                    background: isActive ? `${T.primary}10` : T.white,
                    color: isActive ? T.primary : T.gray600,
                    cursor: 'pointer', transition: 'all 0.15s',
                  }}
                >
                  {tr.label}
                </button>
              );
            })}
          </div>

          {/* Clear all filters */}
          {activeFilterCount > 0 && (
            <button
              onClick={() => {
                setSelectedCategory('');
                setSelectedLevel('');
                setSelectedTimeRange('');
                updateURL('', '', '');
              }}
              style={{
                fontSize: 11, fontWeight: 600, color: T.gray400,
                background: 'none', border: 'none', cursor: 'pointer',
                textDecoration: 'underline', marginLeft: 'auto',
              }}
            >
              清除筛选 ({activeFilterCount})
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>加载中...</div>
      ) : filteredItems.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.3 }}>🎯</div>
          <div>{activeFilterCount > 0 ? '当前筛选条件无匹配结果' : '今日暂无精选内容'}</div>
          {activeFilterCount > 0 && (
            <button
              onClick={() => {
                setSelectedCategory('');
                setSelectedLevel('');
                setSelectedTimeRange('');
                updateURL('', '', '');
              }}
              style={{
                marginTop: 12, fontSize: 12, fontWeight: 600,
                color: T.primary, background: 'none', border: 'none',
                cursor: 'pointer', textDecoration: 'underline',
              }}
            >
              清除筛选
            </button>
          )}
        </div>
      ) : groupByTopic ? (
        /* ── Grouped by topic ── */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingBottom: 40 }}>
          {sortedTopics.map((topic) => {
            const topicItems = topicMap.get(topic.id) || [];
            if (topicItems.length === 0) return null;
            const isExpanded = expandedTopics.has(topic.id) || topicItems.length <= 3;
            const shownItems = isExpanded ? topicItems : topicItems.slice(0, 3);
            const hiddenCount = topicItems.length - 3;

            return (
              <div key={topic.id} style={{
                background: T.white, borderRadius: T.radius,
                border: `1px solid ${T.gray100}`, overflow: 'hidden',
              }}>
                {/* Topic header */}
                <div style={{
                  padding: '14px 20px', borderBottom: `1px solid ${T.gray100}`,
                  background: `linear-gradient(135deg, ${T.primary}06, ${T.primary}02)`,
                  display: 'flex', alignItems: 'center', gap: 10,
                }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: T.gray900 }}>{topic.name}</span>
                  {topic.summary && (
                    <span style={{ fontSize: 12, color: T.gray500 }}>— {topic.summary}</span>
                  )}
                  <span style={{
                    marginLeft: 'auto', fontSize: 11, fontWeight: 600,
                    color: T.primary, background: `${T.primary}10`,
                    padding: '2px 10px', borderRadius: 10,
                  }}>
                    {topicItems.length} 条
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, color: '#FF6B35',
                  }}>
                    TOP {Math.round(topic.best_score)}
                  </span>
                </div>

                {/* Topic items */}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {shownItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
                </div>

                {/* Expand/collapse */}
                {!isExpanded && hiddenCount > 0 && (
                  <button
                    onClick={() => toggleTopic(topic.id)}
                    style={{
                      width: '100%', padding: '10px', border: 'none',
                      background: `${T.gray100}50`, cursor: 'pointer',
                      fontSize: 12, color: T.primary, fontWeight: 600,
                    }}
                  >
                    展开剩余 {hiddenCount} 条 ▼
                  </button>
                )}
                {isExpanded && topicItems.length > 3 && (
                  <button
                    onClick={() => toggleTopic(topic.id)}
                    style={{
                      width: '100%', padding: '10px', border: 'none',
                      background: `${T.gray100}50`, cursor: 'pointer',
                      fontSize: 12, color: T.gray400,
                    }}
                  >
                    收起 ▲
                  </button>
                )}
              </div>
            );
          })}

          {/* Standalone items (no topic) */}
          {standaloneItems.length > 0 && (
            <div>
              {sortedTopics.length > 0 && (
                <h2 style={{ fontSize: 14, fontWeight: 600, color: T.gray500, marginBottom: 12 }}>
                  其他精选 ({standaloneItems.length})
                </h2>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {standaloneItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* ── Flat list mode ── */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 40 }}>
          {filteredItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
        </div>
      )}

      {/* Analysis panel overlay */}
      {selectedAnalysis && <AnalysisPanel analysis={selectedAnalysis} onClose={() => setSelectedAnalysis(null)} />}
    </div>
  );
}


/* ── Card component ── */
function renderCard(
  item: ContentItem, idx: number,
  favorites: Set<number>, handleFav: (id: number) => void,
  setSelectedAnalysis: (a: ContentAnalysis) => void,
) {
  const analysis = (item.analysis || (item as any).analyses?.[0]) as ContentAnalysis | null;
  const isFav = favorites.has(item.id);
  const curationScore = (analysis as any)?.adjusted_curation_score || (analysis as any)?.curation_score || 0;
  const tags: string[] = (analysis as any)?.tags || [];
  const recommendation: string = (analysis as any)?.recommendation || '';

  return (
    <div
      key={item.id}
      style={{
        background: T.white, borderRadius: T.radius,
        border: `1px solid ${T.gray100}`,
        padding: '16px 20px',
        cursor: analysis ? 'pointer' : 'default',
        transition: 'all 0.15s',
      }}
      onClick={() => analysis && setSelectedAnalysis({ ...analysis, _content_id: item.id })}
      onMouseEnter={(e) => { e.currentTarget.style.background = `${T.primary}04`; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = T.white; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          {/* Meta */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: T.gray400 }}>{item.source_name}</span>
            <span style={{ fontSize: 11, color: T.gray300 }}>·</span>
            <span style={{ fontSize: 11, color: T.gray400 }}>{timeAgo(item.published_at || item.crawled_at)}</span>
            {tags.slice(0, 4).map((tag) => (
              <span key={tag} style={{
                fontSize: 10, fontWeight: 600, color: getTagColor(tag),
                background: `${getTagColor(tag)}12`, padding: '1px 8px', borderRadius: 10,
              }}>
                {tag}
              </span>
            ))}
          </div>

          {/* Title */}
          <h3 style={{ fontSize: 14, fontWeight: 600, color: T.gray900, lineHeight: 1.5, marginBottom: 8 }}>
            {item.title}
          </h3>

          {/* Recommendation */}
          {recommendation && (
            <div style={{
              fontSize: 12, color: T.primary, lineHeight: 1.6,
              padding: '6px 10px', marginBottom: 8,
              background: `${T.primary}06`, borderRadius: 6,
              borderLeft: `3px solid ${T.primary}`,
            }}>
              💡 {recommendation}
            </div>
          )}

          {/* Score + Link */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {curationScore > 0 && (
              <span style={{
                fontSize: 12, fontWeight: 700,
                color: curationScore >= 80 ? '#FF6B35' : curationScore >= 70 ? '#F59E0B' : T.primary,
              }}>
                {Math.round(curationScore)}分
              </span>
            )}
            {item.url && (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{
                  fontSize: 11, fontWeight: 600, color: T.teal,
                  textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3,
                  padding: '2px 8px', borderRadius: 4,
                  background: T.tealLight, border: `1px solid ${T.tealBorder}`,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => { (e.target as HTMLElement).style.background = T.teal; (e.target as HTMLElement).style.color = T.white; }}
                onMouseLeave={(e) => { (e.target as HTMLElement).style.background = T.tealLight; (e.target as HTMLElement).style.color = T.teal; }}
              >
                查看原文 ↗
              </a>
            )}
          </div>
        </div>

        <button
          onClick={(e) => { e.stopPropagation(); handleFav(item.id); }}
          style={{
            background: 'none', border: 'none', fontSize: 16, cursor: 'pointer',
            color: isFav ? '#F59E0B' : T.gray300, padding: '4px 6px', lineHeight: 1,
          }}
        >
          {isFav ? '★' : '☆'}
        </button>
      </div>
    </div>
  );
}


/* ── Analysis Panel ── */
function AnalysisPanel({ analysis, onClose }: { analysis: ContentAnalysis; onClose: () => void }) {
  const contentId = (analysis as any)?._content_id || (analysis as any).content_id || 0;
  const [creationPlan, setCreationPlan] = useState<any>(null);
  const [generating, setGenerating] = useState(false);
  const [activePlatform, setActivePlatform] = useState<string | null>(null);

  const handleGenerate = async (platform: string) => {
    if (!contentId) return;
    setActivePlatform(platform);
    setGenerating(true);
    try {
      const plan = await creationApi.generatePlan(contentId, platform);
      setCreationPlan(plan);
    } catch (err) {
      console.error('Failed to generate plan:', err);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 999 }} />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 520, maxWidth: '90vw',
        background: T.white, boxShadow: '-4px 0 24px rgba(0,0,0,0.1)', zIndex: 1000,
        overflowY: 'auto', padding: 32,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: T.gray900 }}>AI 分析报告</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: T.gray400, padding: 4 }}>✕</button>
        </div>

        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 12 }}>精选评分</h3>
          {[
            { label: '精选分', value: (analysis as any)?.curation_score || 0, color: '#FF6B35' },
            { label: '信息密度', value: (analysis as any)?.info_density || 0, color: '#8B5CF6' },
            { label: '可操作性', value: (analysis as any)?.actionability || 0, color: '#3B82F6' },
            { label: '来源权威', value: (analysis as any)?.source_weight || 0, color: '#10B981' },
          ].map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: T.gray500, width: 64 }}>{s.label}</span>
              <div style={{ flex: 1, height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${s.value}%`, height: '100%', background: s.color, borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: T.gray700, width: 24, textAlign: 'right' }}>{Math.round(s.value)}</span>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 12 }}>多维评分</h3>
          {[
            { label: '质量', value: analysis.quality_score, color: '#10B981' },
            { label: '热度', value: analysis.hot_score, color: '#EF4444' },
            { label: '新鲜度', value: analysis.freshness_score, color: '#3B82F6' },
            { label: '创作价值', value: analysis.creator_score, color: T.primary },
            { label: '爆文潜力', value: analysis.viral_score, color: '#F59E0B' },
            { label: '风险', value: analysis.risk_score, color: '#6B7280' },
          ].map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: T.gray500, width: 64 }}>{s.label}</span>
              <div style={{ flex: 1, height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${s.value}%`, height: '100%', background: s.color, borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: T.gray700, width: 24, textAlign: 'right' }}>{Math.round(s.value)}</span>
            </div>
          ))}
        </div>

        {analysis.summary && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>内容摘要</h3>
            <p style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7 }}>{analysis.summary}</p>
          </div>
        )}
        {analysis.key_points?.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>核心观点</h3>
            {analysis.key_points.map((point, i) => (
              <div key={i} style={{ marginBottom: 8, paddingLeft: 12, borderLeft: `3px solid ${T.primary}` }}>
                <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{point}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.creator_angles?.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>创作角度</h3>
            {analysis.creator_angles.map((angle, i) => (
              <div key={i} style={{ marginBottom: 8, paddingLeft: 12, borderLeft: '3px solid #10B981' }}>
                <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{angle}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.title_suggestions?.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>建议标题</h3>
            {analysis.title_suggestions.map((title, i) => (
              <div key={i} style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7, marginBottom: 6 }}>
                <span style={{ color: T.primary, fontWeight: 600 }}>{i + 1}.</span> {title}
              </div>
            ))}
          </div>
        )}

        {/* ── 创作方案生成 ── */}
        <div style={{
          marginTop: 28, padding: '20px', background: `linear-gradient(135deg, ${T.primary}06, #8B5CF606)`,
          borderRadius: T.radius, border: `1px solid ${T.primary}20`,
        }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: T.gray900, marginBottom: 4 }}>
            ✍️ 生成创作方案
          </h3>
          <p style={{ fontSize: 12, color: T.gray500, marginBottom: 14 }}>基于该内容 AI 生成平台专属创作方案</p>

          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {[
              { id: 'xiaohongshu', label: '小红书图文', emoji: '📕' },
              { id: 'short_video', label: '短视频脚本', emoji: '🎬' },
              { id: 'wechat', label: '公众号长文', emoji: '📝' },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => handleGenerate(p.id)}
                disabled={generating}
                style={{
                  flex: 1, padding: '10px 8px', fontSize: 12, fontWeight: 600,
                  background: activePlatform === p.id && creationPlan ? T.primary : T.white,
                  color: activePlatform === p.id && creationPlan ? T.white : T.gray700,
                  border: `1px solid ${activePlatform === p.id && creationPlan ? T.primary : T.gray200}`,
                  borderRadius: T.radiusSm, cursor: generating ? 'wait' : 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                {p.emoji} {p.label}
              </button>
            ))}
          </div>

          {generating && (
            <div style={{ textAlign: 'center', padding: 24, color: T.gray400, fontSize: 13 }}>
              <div style={{ fontSize: 20, marginBottom: 8, animation: 'pulse 1.5s infinite' }}>🤖</div>
              AI 正在生成创作方案...
            </div>
          )}

          {creationPlan && !generating && (
            <CreationPlanDisplay plan={creationPlan} platform={activePlatform || ''} />
          )}
        </div>
      </div>
    </>
  );
}


/* ── Creation Plan Display ── */
function CreationPlanDisplay({ plan, platform }: { plan: any; platform: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = formatPlanText(plan);
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Copy button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleCopy}
          style={{
            fontSize: 11, fontWeight: 600, padding: '4px 12px',
            background: copied ? '#10B981' : T.gray100,
            color: copied ? T.white : T.gray600,
            border: 'none', borderRadius: 4, cursor: 'pointer',
          }}
        >
          {copied ? '✓ 已复制' : '📋 复制全文'}
        </button>
      </div>

      {/* Titles */}
      {plan.titles?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>备选标题</div>
          {plan.titles.map((t: string, i: number) => (
            <div key={i} style={{
              fontSize: 14, fontWeight: 600, color: T.gray900, lineHeight: 1.6,
              padding: '8px 12px', marginBottom: 4,
              background: i === 0 ? `${T.primary}08` : T.gray50,
              borderRadius: 6, borderLeft: i === 0 ? `3px solid ${T.primary}` : '3px solid transparent',
            }}>
              {t}
            </div>
          ))}
        </div>
      )}

      {/* Platform-specific content */}
      {platform === 'xiaohongshu' && plan.structure && (
        <>
          {plan.cover_slogan && (
            <div style={{ padding: '8px 12px', background: '#FF6B3510', borderRadius: 6, borderLeft: '3px solid #FF6B35' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#FF6B35' }}>封面文案：</span>
              <span style={{ fontSize: 13, color: T.gray700 }}> {plan.cover_slogan}</span>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 6 }}>正文结构</div>
            {plan.structure.hook && (
              <div style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6, marginBottom: 6, paddingLeft: 12, borderLeft: `2px solid ${T.primary}` }}>
                🎯 <b>Hook:</b> {plan.structure.hook}
              </div>
            )}
            {plan.structure.points?.map((p: string, i: number) => (
              <div key={i} style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6, marginBottom: 4, paddingLeft: 12, borderLeft: '2px solid #10B981' }}>
                {p}
              </div>
            ))}
            {plan.structure.cta && (
              <div style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6, paddingLeft: 12, borderLeft: '2px solid #F59E0B' }}>
                💬 <b>互动引导:</b> {plan.structure.cta}
              </div>
            )}
          </div>
          {plan.tags?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {plan.tags.map((tag: string) => (
                <span key={tag} style={{ fontSize: 11, color: T.primary, background: `${T.primary}10`, padding: '2px 10px', borderRadius: 12 }}>#{tag}</span>
              ))}
            </div>
          )}
        </>
      )}

      {platform === 'short_video' && plan.scenes && (
        <>
          {plan.hook && (
            <div style={{ padding: '10px 14px', background: '#EF444410', borderRadius: 6, borderLeft: '3px solid #EF4444' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#EF4444' }}>前3秒Hook：</span>
              <span style={{ fontSize: 13, color: T.gray700 }}> {plan.hook}</span>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 8 }}>分镜头脚本（共{plan.total_seconds || 60}秒）</div>
            {plan.scenes.map((scene: any, i: number) => (
              <div key={i} style={{
                padding: '10px 14px', marginBottom: 6, background: T.gray50, borderRadius: 6,
                borderLeft: `3px solid ${T.primary}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: T.primary }}>镜头 {scene.seq}</span>
                  <span style={{ fontSize: 11, color: T.gray400 }}>{scene.seconds}s</span>
                </div>
                <div style={{ fontSize: 12, color: T.gray500, marginBottom: 2 }}>🎬 {scene.visual}</div>
                <div style={{ fontSize: 13, color: T.gray700 }}>{scene.narration}</div>
              </div>
            ))}
          </div>
          {plan.bgm_suggestion && (
            <div style={{ fontSize: 12, color: T.gray500, padding: '8px 12px', background: T.gray50, borderRadius: 6 }}>
              🎵 BGM建议：{plan.bgm_suggestion}
            </div>
          )}
        </>
      )}

      {platform === 'wechat' && plan.outline && (
        <>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 8 }}>
              文章大纲（约{plan.word_count_estimate || 2000}字）
            </div>
            {plan.outline.map((section: any, i: number) => (
              <div key={i} style={{
                padding: '12px 14px', marginBottom: 6, background: T.gray50, borderRadius: 6,
                borderLeft: `3px solid ${i === 0 ? '#FF6B35' : T.primary}`,
              }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.gray900, marginBottom: 4 }}>
                  {section.section}. {section.heading}
                </div>
                {section.points?.map((p: string, j: number) => (
                  <div key={j} style={{ fontSize: 12, color: T.gray600, lineHeight: 1.6, paddingLeft: 8 }}>• {p}</div>
                ))}
                {section.evidence && (
                  <div style={{ fontSize: 11, color: T.gray400, marginTop: 4, fontStyle: 'italic' }}>📎 {section.evidence}</div>
                )}
              </div>
            ))}
          </div>
          {plan.key_quote && (
            <div style={{ padding: '12px 16px', background: `${T.primary}08`, borderRadius: 6, borderLeft: `3px solid ${T.primary}` }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.primary, marginBottom: 4 }}>金句</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, fontStyle: 'italic' }}>「{plan.key_quote}」</div>
            </div>
          )}
          {plan.closing && (
            <div style={{ fontSize: 13, color: T.gray600, padding: '10px 14px', background: T.gray50, borderRadius: 6 }}>
              📌 结尾：{plan.closing}
            </div>
          )}
        </>
      )}

      {plan.tone && (
        <div style={{ fontSize: 11, color: T.gray400, textAlign: 'center' }}>风格建议：{plan.tone}</div>
      )}
    </div>
  );
}


function formatPlanText(plan: any): string {
  const lines: string[] = [];
  if (plan.titles) {
    lines.push('【备选标题】');
    plan.titles.forEach((t: string, i: number) => lines.push(`${i + 1}. ${t}`));
    lines.push('');
  }
  if (plan.cover_slogan) lines.push(`封面文案：${plan.cover_slogan}\n`);
  if (plan.structure) {
    lines.push('【正文结构】');
    if (plan.structure.hook) lines.push(`Hook: ${plan.structure.hook}`);
    plan.structure.points?.forEach((p: string) => lines.push(`- ${p}`));
    if (plan.structure.cta) lines.push(`互动引导: ${plan.structure.cta}`);
    lines.push('');
  }
  if (plan.scenes) {
    lines.push('【分镜头脚本】');
    plan.scenes.forEach((s: any) => lines.push(`镜头${s.seq}(${s.seconds}s): ${s.visual}\n旁白: ${s.narration}`));
    lines.push('');
  }
  if (plan.outline) {
    lines.push('【文章大纲】');
    plan.outline.forEach((s: any) => {
      lines.push(`${s.section}. ${s.heading}`);
      s.points?.forEach((p: string) => lines.push(`  • ${p}`));
    });
    lines.push('');
  }
  if (plan.tags) lines.push(`标签：${plan.tags.map((t: string) => `#${t}`).join(' ')}`);
  if (plan.tone) lines.push(`风格：${plan.tone}`);
  return lines.join('\n');
}
