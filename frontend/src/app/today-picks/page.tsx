'use client';

import React, { useState, useEffect, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { ChevronDown, ChevronUp, Clock3, Columns3, ExternalLink, FileText, Folder, Lightbulb, List, Star, Target } from 'lucide-react';
import { T, CATEGORIES, RECOMMEND_LEVELS, LEVEL_CONFIG } from '@/lib/design-tokens';
import { contentsApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import CategoryChip from '@/components/CategoryChip';
import AnalysisPanel from '@/components/AnalysisPanel';
import { timeAgo, getTagColor, getRecommendLevelLabel } from '@/lib/utils';
import type { ContentItem, ContentAnalysis, TopicInfo } from '@/types';

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

  const updateURL = useCallback((cat: string, level: string, tr: string) => {
    const params = new URLSearchParams();
    if (cat) params.set('category', cat);
    if (level) params.set('level', level);
    if (tr) params.set('time_range', tr);
    const qs = params.toString();
    router.replace(`/today-picks${qs ? '?' + qs : ''}`, { scroll: false });
  }, [router]);

  const setCategory = (cat: string) => { setSelectedCategory(cat); updateURL(cat, selectedLevel, selectedTimeRange); };
  const setLevel = (level: string) => { setSelectedLevel(level); updateURL(selectedCategory, level, selectedTimeRange); };
  const setTimeRange = (tr: string) => { setSelectedTimeRange(tr); updateURL(selectedCategory, selectedLevel, tr); };

  const fetchPicks = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, string> = {};
      if (selectedCategory) params.category = selectedCategory;
      if (selectedTimeRange) params.time_range = selectedTimeRange;
      const res = await contentsApi.todayPicks(params);
      setItems(res.items || []);
      setTopics(res.topics || []);
      setDupCount(res.duplicates_hidden || 0);
    } catch (err) {
      console.error('Failed to fetch today picks:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, selectedTimeRange]);

  useEffect(() => { void fetchPicks(); }, [fetchPicks]);

  const handleFav = async (id: number) => { await toggleFavorite(id); };
  const toggleTopic = (id: number) => {
    setExpandedTopics(prev => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  };

  const filteredItems = useMemo(() => {
    if (!selectedLevel) return items;
    return items.filter(item => {
const analysis = (item.analysis || item.analyses?.[0]) as ContentAnalysis | null;
      if (!analysis) return false;
      const level = getRecommendLevelLabel(analysis);
      return level === selectedLevel;
    });
  }, [items, selectedLevel]);

  const topicMap = new Map<number | null, ContentItem[]>();
  for (const item of filteredItems) {
    const tid = item.topic_id || null;
    if (!topicMap.has(tid)) topicMap.set(tid, []);
    topicMap.get(tid)!.push(item);
  }

  const sortedTopics = topics
    .filter(t => topicMap.has(t.id) && (topicMap.get(t.id)?.length || 0) > 0)
    .sort((a, b) => b.best_score - a.best_score);
  const standaloneItems = topicMap.get(null) || [];
  const activeFilterCount = [selectedCategory, selectedLevel, selectedTimeRange].filter(Boolean).length;

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>当日精选</h1>
          <span style={{ fontSize: 10, fontWeight: 700, color: T.white, background: 'linear-gradient(135deg, #FF6B35, #FF8F65)', padding: '3px 10px', borderRadius: 20 }}>
            CURATED
          </span>
          <button onClick={() => setGroupByTopic(!groupByTopic)}
            style={{ marginLeft: 'auto', fontSize: 11, padding: '4px 12px', borderRadius: 6, border: `1px solid ${groupByTopic ? T.primary : T.gray200}`, background: groupByTopic ? `${T.primary}10` : T.white, color: groupByTopic ? T.primary : T.gray500, cursor: 'pointer', fontWeight: 600 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {groupByTopic ? <Columns3 size={13} /> : <List size={13} />}
              {groupByTopic ? '话题分组' : '平铺列表'}
            </span>
          </button>
        </div>
        <p style={{ fontSize: 13, color: T.gray400 }}>
          精选分 ≥ 60 入选 · 去重后 <b style={{ color: T.primary, fontFamily: T.mono }}>{filteredItems.length}</b> 条
          {dupCount > 0 && <span style={{ color: T.gray400 }}>（隐藏 {dupCount} 条重复）</span>}
          {sortedTopics.length > 0 && groupByTopic && <span> · {sortedTopics.length} 个话题</span>}
        </p>
      </div>

      {/* Filter Bar */}
      <div style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray100}`, padding: '14px 18px', marginBottom: 20 }}>
        <div style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginRight: 8, verticalAlign: 'middle', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Folder size={12} /> 分类
          </span>
          <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap', verticalAlign: 'middle' }}>
            {(CATEGORIES as readonly string[]).map((cat) => (
              <CategoryChip key={cat} name={cat} active={selectedCategory === cat || (!selectedCategory && cat === '全部')} onClick={() => setCategory(cat === '全部' ? '' : cat)} />
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Target size={12} /> 等级
            </span>
            {RECOMMEND_LEVELS.map((level) => {
              const cfg = LEVEL_CONFIG[level];
              const isActive = selectedLevel === level;
              return (
                <button key={level} onClick={() => setLevel(isActive ? '' : level)}
                  style={{ fontSize: 11, fontWeight: isActive ? 600 : 400, padding: '3px 10px', borderRadius: 12, border: isActive ? 'none' : `1px solid ${T.gray200}`, background: isActive ? cfg.bg : T.white, color: isActive ? cfg.color : T.gray600, cursor: 'pointer', transition: 'all 0.15s', whiteSpace: 'nowrap' }}>
                  {level}
                </button>
              );
            })}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.gray500, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Clock3 size={12} /> 时间
            </span>
            {TIME_RANGES.map((tr) => {
              const isActive = selectedTimeRange === tr.value;
              return (
                <button key={tr.value} onClick={() => setTimeRange(isActive ? '' : tr.value)}
                  style={{ fontSize: 11, fontWeight: isActive ? 600 : 400, padding: '3px 10px', borderRadius: 12, border: isActive ? 'none' : `1px solid ${T.gray200}`, background: isActive ? `${T.primary}10` : T.white, color: isActive ? T.primary : T.gray600, cursor: 'pointer', transition: 'all 0.15s' }}>
                  {tr.label}
                </button>
              );
            })}
          </div>
          {activeFilterCount > 0 && (
            <button onClick={() => { setSelectedCategory(''); setSelectedLevel(''); setSelectedTimeRange(''); updateURL('', '', ''); }}
              style={{ fontSize: 11, fontWeight: 600, color: T.gray400, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', marginLeft: 'auto' }}>
              清除筛选 ({activeFilterCount})
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>加载中...</div>
      ) : filteredItems.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <FileText size={34} style={{ marginBottom: 16, opacity: 0.35 }} />
          <div>{activeFilterCount > 0 ? '当前筛选条件无匹配结果' : '今日暂无精选内容'}</div>
          {activeFilterCount > 0 && (
            <button onClick={() => { setSelectedCategory(''); setSelectedLevel(''); setSelectedTimeRange(''); updateURL('', '', ''); }}
              style={{ marginTop: 12, fontSize: 12, fontWeight: 600, color: T.primary, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
              清除筛选
            </button>
          )}
        </div>
      ) : groupByTopic ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingBottom: 40 }}>
          {sortedTopics.map((topic) => {
            const topicItems = topicMap.get(topic.id) || [];
            if (topicItems.length === 0) return null;
            const isExpanded = expandedTopics.has(topic.id) || topicItems.length <= 3;
            const shownItems = isExpanded ? topicItems : topicItems.slice(0, 3);
            const hiddenCount = topicItems.length - 3;
            return (
              <div key={topic.id} style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray100}`, overflow: 'hidden' }}>
                <div style={{ padding: '14px 20px', borderBottom: `1px solid ${T.gray100}`, background: `linear-gradient(135deg, ${T.primary}06, ${T.primary}02)`, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: T.gray900 }}>{topic.name}</span>
                  {topic.summary && <span style={{ fontSize: 12, color: T.gray500 }}>— {topic.summary}</span>}
                  <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, color: T.primary, background: `${T.primary}10`, padding: '2px 10px', borderRadius: 10 }}>{topicItems.length} 条</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#FF6B35' }}>TOP {Math.round(topic.best_score)}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {shownItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
                </div>
                {!isExpanded && hiddenCount > 0 && (
                  <button onClick={() => toggleTopic(topic.id)} style={{ width: '100%', padding: '10px', border: 'none', background: `${T.gray100}50`, cursor: 'pointer', fontSize: 12, color: T.primary, fontWeight: 600 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      展开剩余 {hiddenCount} 条
                      <ChevronDown size={13} strokeWidth={2} />
                    </span>
                  </button>
                )}
                {isExpanded && topicItems.length > 3 && (
                  <button onClick={() => toggleTopic(topic.id)} style={{ width: '100%', padding: '10px', border: 'none', background: `${T.gray100}50`, cursor: 'pointer', fontSize: 12, color: T.gray400 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      收起
                      <ChevronUp size={13} strokeWidth={2} />
                    </span>
                  </button>
                )}
              </div>
            );
          })}
          {standaloneItems.length > 0 && (
            <div>
              {sortedTopics.length > 0 && <h2 style={{ fontSize: 14, fontWeight: 600, color: T.gray500, marginBottom: 12 }}>其他精选 ({standaloneItems.length})</h2>}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {standaloneItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 40 }}>
          {filteredItems.map((item, idx) => renderCard(item, idx, favorites, handleFav, setSelectedAnalysis))}
        </div>
      )}

      {selectedAnalysis && <AnalysisPanel analysis={selectedAnalysis} onClose={() => setSelectedAnalysis(null)} />}
    </div>
  );
}

/* ── Card component ── */
function renderCard(
  item: ContentItem, idx: number,
  favorites: Set<number>, handleFav: (id: number) => void,
  setSelectedAnalysis: (a: ContentAnalysis & { _content_id?: number }) => void,
) {
  const analysis = item.analysis || (item as ContentItem).analyses?.[0];
  const isFav = favorites.has(item.id);
  const curationScore = analysis?.adjusted_curation_score || analysis?.curation_score || 0;
  const _rawTags = analysis?.tags as string | string[] | null | undefined;
  const tags: string[] = Array.isArray(_rawTags) ? _rawTags : (typeof _rawTags === 'string' && _rawTags ? _rawTags.split(',') : []);
  const recommendation: string = analysis?.recommendation || '';

  return (
    <div key={item.id}
      style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray100}`, padding: '16px 20px', cursor: analysis ? 'pointer' : 'default', transition: 'all 0.15s' }}
      onClick={() => analysis && setSelectedAnalysis({ ...analysis, _content_id: item.id })}
      onMouseEnter={(e) => { e.currentTarget.style.background = `${T.primary}04`; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = T.white; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: T.gray400 }}>{item.source_name}</span>
            <span style={{ fontSize: 11, color: T.gray300 }}>·</span>
            <span style={{ fontSize: 11, color: T.gray400 }}>{timeAgo(item.published_at || item.crawled_at)}</span>
            {tags.slice(0, 4).map((tag) => (
              <span key={tag} style={{ fontSize: 10, fontWeight: 600, color: getTagColor(tag), background: `${getTagColor(tag)}12`, padding: '1px 8px', borderRadius: 10 }}>{tag}</span>
            ))}
          </div>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: T.gray900, lineHeight: 1.5, marginBottom: 8 }}>{item.title}</h3>
          {recommendation && (
            <div style={{ fontSize: 12, color: T.primary, lineHeight: 1.6, padding: '6px 10px', marginBottom: 8, background: `${T.primary}06`, borderRadius: 6, borderLeft: `3px solid ${T.primary}`, display: 'flex', gap: 6 }}>
              <Lightbulb size={13} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>{recommendation}</span>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {curationScore > 0 && (
              <span style={{ fontSize: 12, fontWeight: 700, color: curationScore >= 80 ? '#FF6B35' : curationScore >= 70 ? '#F59E0B' : T.primary }}>
                {Math.round(curationScore)}分
              </span>
            )}
            {item.url && (
              <a href={item.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
                style={{ fontSize: 11, fontWeight: 600, color: T.teal, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px', borderRadius: 4, background: T.tealLight, border: `1px solid ${T.tealBorder}`, transition: 'all 0.15s' }}
                onMouseEnter={(e) => { (e.target as HTMLElement).style.background = T.teal; (e.target as HTMLElement).style.color = T.white; }}
                onMouseLeave={(e) => { (e.target as HTMLElement).style.background = T.tealLight; (e.target as HTMLElement).style.color = T.teal; }}>
                查看原文
                <ExternalLink size={12} strokeWidth={2} />
              </a>
            )}
          </div>
        </div>
        <button onClick={(e) => { e.stopPropagation(); handleFav(item.id); }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: isFav ? '#F59E0B' : T.gray300, padding: '4px 6px', display: 'inline-flex', alignItems: 'center' }}>
          <Star size={16} strokeWidth={2} fill={isFav ? '#F59E0B' : 'none'} />
        </button>
      </div>
    </div>
  );
}
