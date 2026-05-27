'use client';

import React, { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  BarChart3,
  ChevronDown,
  ChevronUp,
  Clock3,
  Columns3,
  ExternalLink,
  FileText,
  Filter,
  Flame,
  Layers3,
  List,
  Search,
  SlidersHorizontal,
  Sparkles,
  Star,
  Target,
} from 'lucide-react';
import { CATEGORIES, LEVEL_CONFIG, RECOMMEND_LEVELS, T } from '@/lib/design-tokens';
import { contentsApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import CategoryChip from '@/components/CategoryChip';
import AnalysisPanel from '@/components/AnalysisPanel';
import { getRecommendLevelLabel, getTagColor, timeAgo } from '@/lib/utils';
import type { ContentAnalysis, ContentItem, TopicInfo } from '@/types';

const TIME_RANGES = [
  { value: '', label: '全部' },
  { value: '24h', label: '24h' },
  { value: '48h', label: '48h' },
  { value: '7d', label: '7d' },
] as const;

export default function TodayPicksPageWrapper() {
  return (
    <Suspense fallback={<div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>加载中...</div>}>
      <TodayPicksPage />
    </Suspense>
  );
}

function TodayPicksPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { favorites, toggleFavorite } = useAppContext();

  const [selectedCategory, setSelectedCategory] = useState(searchParams.get('category') || '');
  const [selectedLevel, setSelectedLevel] = useState(searchParams.get('level') || '');
  const [selectedTimeRange, setSelectedTimeRange] = useState(searchParams.get('time_range') || '');
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

  const setCategory = (cat: string) => {
    setSelectedCategory(cat);
    updateURL(cat, selectedLevel, selectedTimeRange);
  };
  const setLevel = (level: string) => {
    const next = selectedLevel === level ? '' : level;
    setSelectedLevel(next);
    updateURL(selectedCategory, next, selectedTimeRange);
  };
  const setTimeRange = (tr: string) => {
    const next = selectedTimeRange === tr ? '' : tr;
    setSelectedTimeRange(next);
    updateURL(selectedCategory, selectedLevel, next);
  };
  const clearFilters = () => {
    setSelectedCategory('');
    setSelectedLevel('');
    setSelectedTimeRange('');
    updateURL('', '', '');
  };

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

  const filteredItems = useMemo(() => {
    if (!selectedLevel) return items;
    return items.filter((item) => {
      const analysis = getAnalysis(item);
      return analysis ? getRecommendLevelLabel(analysis) === selectedLevel : false;
    });
  }, [items, selectedLevel]);

  const topicMap = useMemo(() => {
    const map = new Map<number | null, ContentItem[]>();
    for (const item of filteredItems) {
      const tid = item.topic_id || null;
      if (!map.has(tid)) map.set(tid, []);
      map.get(tid)!.push(item);
    }
    return map;
  }, [filteredItems]);

  const sortedTopics = useMemo(() => (
    topics
      .filter((topic) => topicMap.has(topic.id) && (topicMap.get(topic.id)?.length || 0) > 0)
      .sort((a, b) => b.best_score - a.best_score)
  ), [topics, topicMap]);

  const standaloneItems = topicMap.get(null) || [];
  const activeFilterCount = [selectedCategory, selectedLevel, selectedTimeRange].filter(Boolean).length;
  const sortedItems = useMemo(() => [...filteredItems].sort((a, b) => scoreOf(b) - scoreOf(a)), [filteredItems]);
  const leadItem = sortedItems[0] || null;
  const sourceCount = new Set(filteredItems.map((item) => item.source_name).filter(Boolean)).size;
  const avgScore = filteredItems.length
    ? Math.round(filteredItems.reduce((sum, item) => sum + scoreOf(item), 0) / filteredItems.length)
    : 0;
  const levelStats = useMemo(() => {
    return RECOMMEND_LEVELS.map((level) => ({
      level,
      count: filteredItems.filter((item) => {
        const analysis = getAnalysis(item);
        return analysis ? getRecommendLevelLabel(analysis) === level : false;
      }).length,
    }));
  }, [filteredItems]);

  const handleFav = async (id: number) => { await toggleFavorite(id); };
  const toggleTopic = (id: number) => {
    setExpandedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

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
        <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ fontSize: 20, fontWeight: 900, color: T.gray900 }}>当日精选</h1>
              <span style={{
                fontSize: 10,
                fontWeight: 800,
                color: T.primary,
                background: T.primaryLight,
                border: `1px solid ${T.primaryBorder}`,
                padding: '3px 8px',
                borderRadius: 999,
                fontFamily: T.mono,
              }}>
                CURATION DESK
              </span>
            </div>
            <p style={{ fontSize: 12, color: T.gray400, marginTop: 3 }}>
              从算法候选中筛出可写选题，按话题、质量和来源做二次判断
            </p>
          </div>
          <button
            onClick={() => setGroupByTopic(!groupByTopic)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              fontSize: 12,
              fontWeight: 700,
              color: groupByTopic ? T.primary : T.gray600,
              background: groupByTopic ? T.primaryLight : T.white,
              border: `1px solid ${groupByTopic ? T.primaryBorder : T.gray200}`,
              borderRadius: T.radiusSm,
              padding: '8px 12px',
              cursor: 'pointer',
            }}
          >
            {groupByTopic ? <Columns3 size={15} /> : <List size={15} />}
            {groupByTopic ? '话题视图' : '列表视图'}
          </button>
        </div>
      </div>

      <div style={{
        maxWidth: 1180,
        margin: '24px auto 0',
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) 260px',
        gap: 18,
        alignItems: 'start',
      }}>
        <main style={{ minWidth: 0 }}>
          <OverviewStrip
            total={filteredItems.length}
            sourceCount={sourceCount}
            topicCount={sortedTopics.length}
            avgScore={avgScore}
            dupCount={dupCount}
          />

          {leadItem && <LeadPick item={leadItem} isFav={favorites.has(leadItem.id)} onFav={handleFav} onOpen={setSelectedAnalysis} />}

          {loading ? (
            <EmptyState icon={Sparkles} title="精选加载中" desc="正在读取算法筛选结果..." />
          ) : filteredItems.length === 0 ? (
            <EmptyState
              icon={FileText}
              title={activeFilterCount > 0 ? '筛选后没有匹配内容' : '当前没有精选内容'}
              desc={activeFilterCount > 0 ? '可以放宽等级、分类或时间范围。' : '等待内容同步和分析完成后会自动出现。'}
              action={activeFilterCount > 0 ? { label: '清除筛选', onClick: clearFilters } : undefined}
            />
          ) : groupByTopic ? (
            <TopicBoard
              topics={sortedTopics}
              topicMap={topicMap}
              standaloneItems={standaloneItems}
              expandedTopics={expandedTopics}
              onToggleTopic={toggleTopic}
              favorites={favorites}
              onFav={handleFav}
              onOpen={setSelectedAnalysis}
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 40 }}>
              {sortedItems.map((item, idx) => (
                <PickCard key={item.id} item={item} rank={idx + 1} isFav={favorites.has(item.id)} onFav={handleFav} onOpen={setSelectedAnalysis} />
              ))}
            </div>
          )}
        </main>

        <aside style={{ position: 'sticky', top: 88, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <FilterPanel
            selectedCategory={selectedCategory}
            selectedLevel={selectedLevel}
            selectedTimeRange={selectedTimeRange}
            activeFilterCount={activeFilterCount}
            onCategory={setCategory}
            onLevel={setLevel}
            onTimeRange={setTimeRange}
            onClear={clearFilters}
          />
          <QualityPanel levelStats={levelStats} total={filteredItems.length} />
        </aside>
      </div>

      {selectedAnalysis && <AnalysisPanel analysis={selectedAnalysis} onClose={() => setSelectedAnalysis(null)} />}
    </div>
  );
}

function OverviewStrip({
  total,
  sourceCount,
  topicCount,
  avgScore,
  dupCount,
}: {
  total: number;
  sourceCount: number;
  topicCount: number;
  avgScore: number;
  dupCount: number;
}) {
  const stats = [
    { label: '精选内容', value: total, hint: '去重后', icon: Target, color: T.primary },
    { label: '平均分', value: avgScore || '-', hint: '算法校准', icon: BarChart3, color: T.teal },
    { label: '话题组', value: topicCount, hint: '聚类结果', icon: Layers3, color: T.purple },
    { label: '来源', value: sourceCount, hint: dupCount ? `隐藏重复 ${dupCount}` : '有效信源', icon: Search, color: T.amber },
  ];

  return (
    <section style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
      gap: 10,
      marginBottom: 16,
    }}>
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <div key={stat.label} style={{
            background: T.white,
            border: `1px solid ${T.gray200}`,
            borderRadius: T.radius,
            padding: '14px 15px',
            minWidth: 0,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Icon size={15} color={stat.color} strokeWidth={2.2} />
              <span style={{ fontSize: 12, color: T.gray500, fontWeight: 700 }}>{stat.label}</span>
            </div>
            <div style={{ fontSize: 28, lineHeight: 1, fontWeight: 900, color: T.gray900, fontFamily: T.mono }}>
              {stat.value}
            </div>
            <div style={{ marginTop: 5, fontSize: 11, color: T.gray400 }}>{stat.hint}</div>
          </div>
        );
      })}
    </section>
  );
}

function LeadPick({
  item,
  isFav,
  onFav,
  onOpen,
}: {
  item: ContentItem;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (a: ContentAnalysis & { _content_id?: number }) => void;
}) {
  const analysis = getAnalysis(item);
  const score = scoreOf(item);
  const tags = tagsOf(analysis);
  const recommendation = analysis?.recommendation || analysis?.recommended_reason || item.summary || '';

  return (
    <section style={{
      position: 'relative',
      overflow: 'hidden',
      background: T.white,
      color: T.gray900,
      borderRadius: T.radius,
      border: `1px solid ${T.gray200}`,
      padding: '22px 24px',
      marginBottom: 16,
      boxShadow: '0 16px 38px rgba(15, 23, 42, 0.06)',
    }}>
      <div style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 4,
        background: `linear-gradient(180deg, ${T.primary}, ${T.teal})`,
      }} />
      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 110px', gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 11,
              fontWeight: 800,
              color: T.primary,
              background: T.primaryLight,
              border: `1px solid ${T.primaryBorder}`,
              padding: '3px 8px',
              borderRadius: 999,
            }}>
              <Flame size={13} /> 今日主推
            </span>
            <span style={{ fontSize: 11, color: T.gray500 }}>{item.source_name}</span>
            {tags.slice(0, 3).map((tag) => (
              <span key={tag} style={{ fontSize: 10, fontWeight: 700, color: T.gray600, background: T.gray50, border: `1px solid ${T.gray200}`, padding: '2px 7px', borderRadius: 999 }}>
                {tag}
              </span>
            ))}
          </div>
          <h2 style={{ fontSize: 23, lineHeight: 1.38, fontWeight: 900, marginBottom: 10, color: T.gray900 }}>
            {item.title}
          </h2>
          {recommendation && (
            <p style={{ fontSize: 13, lineHeight: 1.75, color: T.gray600, maxWidth: 680 }}>
              {recommendation}
            </p>
          )}
          <PickActions item={item} analysis={analysis} isFav={isFav} onFav={onFav} onOpen={onOpen} />
        </div>
        <div style={{
          alignSelf: 'stretch',
          border: `1px solid ${T.primaryBorder}`,
          borderRadius: T.radiusSm,
          background: T.primaryLight,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div style={{ fontSize: 11, color: T.gray500, marginBottom: 5 }}>SCORE</div>
          <div style={{ fontSize: 40, fontWeight: 900, fontFamily: T.mono, color: T.primary }}>{Math.round(score)}</div>
        </div>
      </div>
    </section>
  );
}

function FilterPanel({
  selectedCategory,
  selectedLevel,
  selectedTimeRange,
  activeFilterCount,
  onCategory,
  onLevel,
  onTimeRange,
  onClear,
}: {
  selectedCategory: string;
  selectedLevel: string;
  selectedTimeRange: string;
  activeFilterCount: number;
  onCategory: (cat: string) => void;
  onLevel: (level: string) => void;
  onTimeRange: (range: string) => void;
  onClear: () => void;
}) {
  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: '16px' }}>
      <PanelTitle icon={SlidersHorizontal} title="筛选台" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <FilterLabel icon={Clock3}>时间范围</FilterLabel>
          <Segmented values={TIME_RANGES} active={selectedTimeRange} onChange={onTimeRange} />
        </div>
        <div>
          <FilterLabel icon={Target}>推荐等级</FilterLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {RECOMMEND_LEVELS.map((level) => {
              const cfg = LEVEL_CONFIG[level];
              const active = selectedLevel === level;
              return (
                <button key={level} onClick={() => onLevel(level)} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  width: '100%',
                  border: `1px solid ${active ? cfg.border : T.gray200}`,
                  background: active ? cfg.bg : T.white,
                  color: active ? cfg.color : T.gray600,
                  borderRadius: T.radiusSm,
                  padding: '7px 9px',
                  fontSize: 12,
                  fontWeight: active ? 800 : 600,
                  cursor: 'pointer',
                  textAlign: 'left',
                }}>
                  <span style={{ width: 7, height: 7, borderRadius: 999, background: cfg.dot }} />
                  {level}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <FilterLabel icon={Filter}>分类</FilterLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(CATEGORIES as readonly string[]).map((cat) => (
              <CategoryChip
                key={cat}
                name={cat}
                active={selectedCategory === cat || (!selectedCategory && cat === '全部')}
                onClick={() => onCategory(cat === '全部' ? '' : cat)}
              />
            ))}
          </div>
        </div>
        {activeFilterCount > 0 && (
          <button onClick={onClear} style={{
            border: 'none',
            background: T.gray100,
            color: T.gray600,
            borderRadius: T.radiusSm,
            padding: '8px 10px',
            fontSize: 12,
            fontWeight: 800,
            cursor: 'pointer',
          }}>
            清除筛选 ({activeFilterCount})
          </button>
        )}
      </div>
    </section>
  );
}

function QualityPanel({
  levelStats,
  total,
}: {
  levelStats: Array<{ level: string; count: number }>;
  total: number;
}) {
  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: '16px' }}>
      <PanelTitle icon={BarChart3} title="质量分布" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {levelStats.map(({ level, count }) => {
          const cfg = LEVEL_CONFIG[level];
          const width = total > 0 ? Math.max(6, Math.round((count / total) * 100)) : 0;
          return (
            <div key={level}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: T.gray600, marginBottom: 5 }}>
                <span>{level}</span>
                <span style={{ fontFamily: T.mono, fontWeight: 800 }}>{count}</span>
              </div>
              <div style={{ height: 7, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ width: `${width}%`, height: '100%', background: cfg.dot, borderRadius: 999 }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TopicBoard({
  topics,
  topicMap,
  standaloneItems,
  expandedTopics,
  onToggleTopic,
  favorites,
  onFav,
  onOpen,
}: {
  topics: TopicInfo[];
  topicMap: Map<number | null, ContentItem[]>;
  standaloneItems: ContentItem[];
  expandedTopics: Set<number>;
  onToggleTopic: (id: number) => void;
  favorites: Set<number>;
  onFav: (id: number) => void;
  onOpen: (a: ContentAnalysis & { _content_id?: number }) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 40 }}>
      {topics.map((topic) => {
        const topicItems = topicMap.get(topic.id) || [];
        if (topicItems.length === 0) return null;
        const sortedItems = [...topicItems].sort((a, b) => scoreOf(b) - scoreOf(a));
        const isExpanded = expandedTopics.has(topic.id) || sortedItems.length <= 3;
        const shownItems = isExpanded ? sortedItems : sortedItems.slice(0, 3);
        const hiddenCount = sortedItems.length - 3;
        return (
          <section key={topic.id} style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, overflow: 'hidden' }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) auto auto',
              gap: 10,
              alignItems: 'center',
              padding: '14px 18px',
              borderBottom: `1px solid ${T.gray100}`,
              background: '#FBFCFE',
            }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 900, color: T.gray900, lineHeight: 1.4 }}>{topic.name}</div>
                {topic.summary && <div style={{ fontSize: 12, color: T.gray500, marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{topic.summary}</div>}
              </div>
              <span style={{ fontSize: 11, fontWeight: 800, color: T.primary, background: T.primaryLight, border: `1px solid ${T.primaryBorder}`, padding: '3px 8px', borderRadius: 999 }}>
                {topicItems.length} 条
              </span>
              <span style={{ fontSize: 11, fontWeight: 900, color: T.gray800, fontFamily: T.mono }}>
                TOP {Math.round(topic.best_score)}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {shownItems.map((item, idx) => (
                <PickCard key={item.id} item={item} rank={idx + 1} isFav={favorites.has(item.id)} onFav={onFav} onOpen={onOpen} flush />
              ))}
            </div>
            {!isExpanded && hiddenCount > 0 && (
              <TopicToggle onClick={() => onToggleTopic(topic.id)} label={`展开剩余 ${hiddenCount} 条`} icon={ChevronDown} />
            )}
            {isExpanded && sortedItems.length > 3 && (
              <TopicToggle onClick={() => onToggleTopic(topic.id)} label="收起" icon={ChevronUp} muted />
            )}
          </section>
        );
      })}
      {standaloneItems.length > 0 && (
        <section>
          {topics.length > 0 && <SectionHeading title="其他精选" count={standaloneItems.length} />}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[...standaloneItems].sort((a, b) => scoreOf(b) - scoreOf(a)).map((item, idx) => (
              <PickCard key={item.id} item={item} rank={idx + 1} isFav={favorites.has(item.id)} onFav={onFav} onOpen={onOpen} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function PickCard({
  item,
  rank,
  isFav,
  onFav,
  onOpen,
  flush = false,
}: {
  item: ContentItem;
  rank: number;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (a: ContentAnalysis & { _content_id?: number }) => void;
  flush?: boolean;
}) {
  const analysis = getAnalysis(item);
  const score = scoreOf(item);
  const tags = tagsOf(analysis);
  const recommendation = analysis?.recommendation || analysis?.recommended_reason || item.summary || '';

  return (
    <article
      onClick={() => analysis && onOpen({ ...analysis, _content_id: item.id })}
      style={{
        display: 'grid',
        gridTemplateColumns: '42px minmax(0, 1fr) 52px',
        gap: 12,
        alignItems: 'start',
        background: flush ? 'transparent' : T.white,
        border: flush ? 'none' : `1px solid ${T.gray200}`,
        borderBottom: flush ? `1px solid ${T.gray100}` : `1px solid ${T.gray200}`,
        borderRadius: flush ? 0 : T.radius,
        padding: '15px 18px',
        cursor: analysis ? 'pointer' : 'default',
        transition: 'background 0.15s ease, border-color 0.15s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = flush ? '#FBFCFE' : T.white;
        e.currentTarget.style.borderColor = T.primaryBorder;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = flush ? 'transparent' : T.white;
        e.currentTarget.style.borderColor = flush ? T.gray100 : T.gray200;
      }}
    >
      <div style={{
        width: 32,
        height: 32,
        borderRadius: T.radiusSm,
        background: rank <= 3 ? T.primaryLight : T.gray100,
        color: rank <= 3 ? T.primary : T.gray500,
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: T.gray500, fontWeight: 700 }}>{item.source_name}</span>
          <span style={{ fontSize: 11, color: T.gray300 }}>/</span>
          <span style={{ fontSize: 11, color: T.gray400 }}>{timeAgo(item.published_at || item.crawled_at)}</span>
          {item.category && <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, padding: '2px 7px', borderRadius: 999 }}>{item.category}</span>}
          {tags.slice(0, 3).map((tag) => (
            <span key={tag} style={{ fontSize: 10, fontWeight: 700, color: getTagColor(tag), background: `${getTagColor(tag)}12`, padding: '2px 7px', borderRadius: 999 }}>
              {tag}
            </span>
          ))}
        </div>
        <h3 style={{ fontSize: 15, fontWeight: 800, color: T.gray900, lineHeight: 1.45, marginBottom: recommendation ? 7 : 0 }}>
          {item.title}
        </h3>
        {recommendation && (
          <p style={{ fontSize: 12, color: T.gray500, lineHeight: 1.65, marginBottom: 10 }}>
            {recommendation}
          </p>
        )}
        <PickActions item={item} analysis={analysis} isFav={isFav} onFav={onFav} onOpen={onOpen} />
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 22, lineHeight: 1, fontWeight: 900, color: score >= 80 ? T.primary : score >= 70 ? T.amber : T.teal, fontFamily: T.mono }}>
          {Math.round(score)}
        </div>
        <div style={{ fontSize: 10, color: T.gray400, marginTop: 4 }}>分</div>
      </div>
    </article>
  );
}

function PickActions({
  item,
  analysis,
  isFav,
  onFav,
  onOpen,
  dark = false,
}: {
  item: ContentItem;
  analysis?: ContentAnalysis | null;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (a: ContentAnalysis & { _content_id?: number }) => void;
  dark?: boolean;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: dark ? 16 : 0 }}>
      {analysis && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpen({ ...analysis, _content_id: item.id });
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            border: dark ? '1px solid rgba(255,255,255,0.16)' : `1px solid ${T.gray200}`,
            background: dark ? 'rgba(255,255,255,0.08)' : T.white,
            color: dark ? '#E5E7EB' : T.gray600,
            borderRadius: T.radiusXs,
            padding: '5px 9px',
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          <Target size={13} /> 分析
        </button>
      )}
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            border: dark ? '1px solid rgba(255,255,255,0.16)' : `1px solid ${T.tealBorder}`,
            background: dark ? 'rgba(255,255,255,0.08)' : T.tealLight,
            color: dark ? '#E5E7EB' : T.teal,
            borderRadius: T.radiusXs,
            padding: '5px 9px',
            fontSize: 11,
            fontWeight: 700,
            textDecoration: 'none',
          }}
        >
          原文 <ExternalLink size={13} />
        </a>
      )}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onFav(item.id);
        }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          border: dark ? '1px solid rgba(255,255,255,0.16)' : `1px solid ${T.gray200}`,
          background: dark ? 'rgba(255,255,255,0.08)' : T.white,
          color: isFav ? '#F59E0B' : dark ? '#CBD5E1' : T.gray400,
          borderRadius: T.radiusXs,
          padding: '5px 9px',
          fontSize: 11,
          fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        <Star size={13} fill={isFav ? '#F59E0B' : 'none'} /> 收藏
      </button>
    </div>
  );
}

function Segmented({
  values,
  active,
  onChange,
}: {
  values: readonly { value: string; label: string }[];
  active: string;
  onChange: (value: string) => void;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${values.length}, 1fr)`, gap: 4, background: T.gray100, borderRadius: T.radiusSm, padding: 4 }}>
      {values.map((item) => {
        const selected = active === item.value;
        return (
          <button
            key={item.value}
            onClick={() => onChange(item.value)}
            style={{
              border: 'none',
              background: selected ? T.white : 'transparent',
              color: selected ? T.primary : T.gray500,
              borderRadius: T.radiusXs,
              padding: '5px 0',
              fontSize: 11,
              fontWeight: selected ? 900 : 700,
              cursor: 'pointer',
              boxShadow: selected ? '0 1px 3px rgba(15, 23, 42, 0.08)' : 'none',
            }}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

function PanelTitle({ icon: Icon, title }: { icon: typeof SlidersHorizontal; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 14 }}>
      <Icon size={15} color={T.primary} strokeWidth={2.2} />
      <span style={{ fontSize: 14, fontWeight: 900, color: T.gray900 }}>{title}</span>
    </div>
  );
}

function FilterLabel({ icon: Icon, children }: { icon: typeof Clock3; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 7, fontSize: 11, fontWeight: 900, color: T.gray500 }}>
      <Icon size={12} strokeWidth={2.2} />
      {children}
    </div>
  );
}

function TopicToggle({
  onClick,
  label,
  icon: Icon,
  muted = false,
}: {
  onClick: () => void;
  label: string;
  icon: typeof ChevronDown;
  muted?: boolean;
}) {
  return (
    <button onClick={onClick} style={{
      width: '100%',
      padding: '10px',
      border: 'none',
      background: '#FBFCFE',
      cursor: 'pointer',
      fontSize: 12,
      color: muted ? T.gray400 : T.primary,
      fontWeight: 800,
    }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {label}
        <Icon size={13} strokeWidth={2} />
      </span>
    </button>
  );
}

function SectionHeading({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 10px' }}>
      <h2 style={{ fontSize: 14, fontWeight: 900, color: T.gray800 }}>{title}</h2>
      <span style={{ fontSize: 11, color: T.gray400, fontFamily: T.mono }}>{count}</span>
    </div>
  );
}

function EmptyState({
  icon: Icon,
  title,
  desc,
  action,
}: {
  icon: typeof FileText;
  title: string;
  desc: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: '64px 24px', textAlign: 'center', color: T.gray400 }}>
      <Icon size={34} style={{ marginBottom: 14, opacity: 0.42 }} />
      <div style={{ fontSize: 15, fontWeight: 900, color: T.gray700 }}>{title}</div>
      <div style={{ fontSize: 12, marginTop: 6 }}>{desc}</div>
      {action && (
        <button onClick={action.onClick} style={{
          marginTop: 14,
          border: `1px solid ${T.primaryBorder}`,
          background: T.primaryLight,
          color: T.primary,
          borderRadius: T.radiusSm,
          padding: '7px 12px',
          fontSize: 12,
          fontWeight: 800,
          cursor: 'pointer',
        }}>
          {action.label}
        </button>
      )}
    </div>
  );
}

function getAnalysis(item: ContentItem): ContentAnalysis | undefined {
  return item.analysis || item.analyses?.[0];
}

function scoreOf(item: ContentItem): number {
  const analysis = getAnalysis(item);
  return analysis?.adjusted_curation_score || analysis?.curation_score || 0;
}

function tagsOf(analysis?: ContentAnalysis | null): string[] {
  const rawTags = analysis?.tags as string | string[] | null | undefined;
  if (Array.isArray(rawTags)) return rawTags;
  if (typeof rawTags === 'string' && rawTags) return rawTags.split(',').map((tag) => tag.trim()).filter(Boolean);
  return [];
}
