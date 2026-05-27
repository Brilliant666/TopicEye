'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Flame,
  Gauge,
  Inbox,
  Layers3,
  Radar,
  SlidersHorizontal,
  Sparkles,
  Star,
  Target,
  Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { CATEGORIES, T } from '@/lib/design-tokens';
import { viralApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import CategoryChip from '@/components/CategoryChip';
import AnalysisPanel from '@/components/AnalysisPanel';
import type { ContentAnalysis, ContentItem } from '@/types';

const TIME_RANGES = [
  { value: 24, label: '24h' },
  { value: 48, label: '48h' },
  { value: 168, label: '7d' },
] as const;

const PAGE_SIZE = 20;

type AnalysisWithMeta = ContentAnalysis & { _content_id?: number };

export default function LowFollowerViralPage() {
  const { favorites, toggleFavorite } = useAppContext();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hours, setHours] = useState<number>(48);
  const [category, setCategory] = useState('');
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisWithMeta | null>(null);

  const fetchItems = useCallback(async (targetPage: number) => {
    try {
      setLoading(true);
      const res = await viralApi.list({
        page: targetPage,
        hours,
        category: category || undefined,
        page_size: PAGE_SIZE,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Failed to fetch LFV items:', err);
    } finally {
      setLoading(false);
    }
  }, [hours, category]);

  useEffect(() => { void fetchItems(page); }, [fetchItems, page]);
  useEffect(() => { setPage(1); }, [hours, category]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const startItem = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const endItem = Math.min(page * PAGE_SIZE, total);
  const topItem = items[0] || null;
  const avgLfv = items.length ? Math.round(items.reduce((sum, item) => sum + lfvScore(item), 0) / items.length) : 0;
  const strongCount = items.filter((item) => lfvScore(item) >= 40).length;
  const lowAuthorityCount = items.filter((item) => sourceWeight(item) <= 35).length;
  const sourceCount = new Set(items.map((item) => item.source_name).filter(Boolean)).size;

  const openAnalysis = (item: ContentItem) => {
    const analysis = getAnalysis(item);
    if (analysis) setSelectedAnalysis({ ...analysis, _content_id: item.id });
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
        <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ fontSize: 20, fontWeight: 900, color: T.gray900 }}>低粉爆文</h1>
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
                BREAKOUT RADAR
              </span>
            </div>
            <p style={{ marginTop: 3, fontSize: 12, color: T.gray400 }}>
              发现低权威来源里的高传播样本，优先捕捉小号突破信号
            </p>
          </div>
          <div style={{ display: 'flex', gap: 6, background: T.gray100, borderRadius: T.radiusSm, padding: 4 }}>
            {TIME_RANGES.map((range) => {
              const active = hours === range.value;
              return (
                <button
                  key={range.value}
                  onClick={() => setHours(range.value)}
                  style={{
                    border: 'none',
                    borderRadius: T.radiusXs,
                    background: active ? T.white : 'transparent',
                    color: active ? T.primary : T.gray500,
                    boxShadow: active ? '0 1px 3px rgba(15,23,42,0.08)' : 'none',
                    padding: '6px 10px',
                    fontSize: 11,
                    fontWeight: active ? 900 : 700,
                    cursor: 'pointer',
                  }}
                >
                  {range.label}
                </button>
              );
            })}
          </div>
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
          <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginBottom: 16 }}>
            <StatCard icon={Radar} label="突破样本" value={total} hint={`${startItem}-${endItem}`} color={T.primary} />
            <StatCard icon={Gauge} label="平均 LFV" value={avgLfv || '-'} hint="当前页" color={T.teal} />
            <StatCard icon={Zap} label="强突破" value={strongCount} hint="LFV >= 40" color={T.amber} />
            <StatCard icon={Layers3} label="来源数" value={sourceCount} hint={`${lowAuthorityCount} 个低权威信号`} color={T.purple} />
          </section>

          {topItem && !loading && (
            <HeroBreakout item={topItem} isFav={favorites.has(topItem.id)} onFav={toggleFavorite} onOpen={openAnalysis} />
          )}

          {loading ? (
            <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 80, textAlign: 'center', color: T.gray400 }}>
              <Sparkles size={30} style={{ marginBottom: 12, opacity: 0.5 }} />
              <div style={{ fontSize: 14 }}>扫描突破样本...</div>
            </div>
          ) : items.length === 0 ? (
            <EmptyState />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {items.map((item, index) => (
                <BreakoutCard
                  key={item.id}
                  item={item}
                  rank={(page - 1) * PAGE_SIZE + index + 1}
                  isFav={favorites.has(item.id)}
                  onFav={toggleFavorite}
                  onOpen={openAnalysis}
                />
              ))}
            </div>
          )}

          {!loading && totalPages > 1 && (
            <Pagination page={page} totalPages={totalPages} onPage={setPage} />
          )}
        </main>

        <aside style={{ position: 'sticky', top: 88, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <FilterPanel category={category} setCategory={setCategory} />
          <SignalPanel items={items} />
        </aside>
      </div>

      {selectedAnalysis && (
        <AnalysisPanel analysis={selectedAnalysis} onClose={() => setSelectedAnalysis(null)} />
      )}
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
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: '15px 16px', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Icon size={15} color={color} strokeWidth={2.2} />
        <span style={{ fontSize: 12, color: T.gray500, fontWeight: 800 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, lineHeight: 1, fontWeight: 900, fontFamily: T.mono, color: T.gray900 }}>{value}</div>
      <div style={{ marginTop: 6, fontSize: 11, color: T.gray400 }}>{hint}</div>
    </div>
  );
}

function HeroBreakout({
  item,
  isFav,
  onFav,
  onOpen,
}: {
  item: ContentItem;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (item: ContentItem) => void;
}) {
  const analysis = getAnalysis(item);
  const score = lfvScore(item);
  const obscure = obscureFactor(item);
  const authority = sourceWeight(item);
  const reason = analysis?.recommendation || analysis?.recommended_reason || item.summary || '';

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
      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 132px', gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 11,
              fontWeight: 900,
              color: T.primary,
              background: T.primaryLight,
              border: `1px solid ${T.primaryBorder}`,
              padding: '3px 8px',
              borderRadius: 999,
            }}>
              <Flame size={13} /> 最强突破
            </span>
            <span style={{ fontSize: 11, color: T.gray500 }}>{item.source_name}</span>
            <SignalPill label={`隐蔽 x${obscure.toFixed(2)}`} />
            <SignalPill label={`源权威 ${Math.round(authority)}`} />
          </div>
          <h2 style={{ fontSize: 23, lineHeight: 1.38, fontWeight: 900, marginBottom: 10, color: T.gray900 }}>
            {item.title}
          </h2>
          {reason && <p style={{ fontSize: 13, lineHeight: 1.75, color: T.gray600, maxWidth: 680 }}>{reason}</p>}
          <ActionRow item={item} isFav={isFav} onFav={onFav} onOpen={onOpen} />
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
          <div style={{ fontSize: 11, color: T.gray500, marginBottom: 6 }}>LFV</div>
          <div style={{ fontSize: 42, lineHeight: 1, fontWeight: 900, fontFamily: T.mono, color: T.primary }}>
            {score.toFixed(1)}
          </div>
        </div>
      </div>
    </section>
  );
}

function BreakoutCard({
  item,
  rank,
  isFav,
  onFav,
  onOpen,
}: {
  item: ContentItem;
  rank: number;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (item: ContentItem) => void;
}) {
  const analysis = getAnalysis(item);
  const score = lfvScore(item);
  const authority = sourceWeight(item);
  const obscure = obscureFactor(item);
  const reason = analysis?.recommendation || analysis?.recommended_reason || item.summary || '';

  return (
    <article
      onClick={() => analysis && onOpen(item)}
      style={{
        display: 'grid',
        gridTemplateColumns: '44px minmax(0, 1fr) 76px',
        gap: 12,
        alignItems: 'start',
        background: T.white,
        border: `1px solid ${T.gray200}`,
        borderRadius: T.radius,
        padding: '16px 18px',
        cursor: analysis ? 'pointer' : 'default',
        transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = T.primaryBorder;
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(15,23,42,0.07)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = T.gray200;
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div style={{
        width: 34,
        height: 34,
        borderRadius: T.radiusSm,
        background: score >= 40 ? T.primaryLight : score >= 25 ? T.amberLight : T.gray100,
        color: score >= 40 ? T.primary : score >= 25 ? T.amber : T.gray500,
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
          <span style={{ fontSize: 12, color: T.gray500, fontWeight: 800 }}>{item.source_name}</span>
          {item.category && <SignalPill label={item.category} />}
          <SignalPill label={`源权威 ${Math.round(authority)}`} />
          <SignalPill label={`隐蔽 x${obscure.toFixed(2)}`} tone={authority <= 35 ? 'good' : 'muted'} />
        </div>
        <h3 style={{ fontSize: 15, lineHeight: 1.45, fontWeight: 900, color: T.gray900, marginBottom: reason ? 7 : 0 }}>
          {item.title}
        </h3>
        {reason && (
          <p style={{ fontSize: 12, color: T.gray500, lineHeight: 1.65, marginBottom: 10 }}>
            {reason}
          </p>
        )}
        <ActionRow item={item} isFav={isFav} onFav={onFav} onOpen={onOpen} />
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 24, lineHeight: 1, fontWeight: 900, color: score >= 40 ? T.primary : score >= 25 ? T.amber : T.teal, fontFamily: T.mono }}>
          {score.toFixed(1)}
        </div>
        <div style={{ fontSize: 10, color: T.gray400, marginTop: 4 }}>LFV</div>
      </div>
    </article>
  );
}

function ActionRow({
  item,
  isFav,
  onFav,
  onOpen,
  dark = false,
}: {
  item: ContentItem;
  isFav: boolean;
  onFav: (id: number) => void;
  onOpen: (item: ContentItem) => void;
  dark?: boolean;
}) {
  const analysis = getAnalysis(item);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: dark ? 16 : 0 }}>
      {analysis && (
        <button
          onClick={(event) => {
            event.stopPropagation();
            onOpen(item);
          }}
          style={actionStyle(dark)}
        >
          <Target size={13} /> 分析
        </button>
      )}
      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => event.stopPropagation()}
          style={{ ...actionStyle(dark), textDecoration: 'none' }}
        >
          原文 <ExternalLink size={13} />
        </a>
      )}
      <button
        onClick={(event) => {
          event.stopPropagation();
          onFav(item.id);
        }}
        style={{
          ...actionStyle(dark),
          color: isFav ? '#F59E0B' : dark ? '#CBD5E1' : T.gray400,
        }}
      >
        <Star size={13} fill={isFav ? '#F59E0B' : 'none'} /> 收藏
      </button>
    </div>
  );
}

function actionStyle(dark: boolean): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    border: dark ? '1px solid rgba(255,255,255,0.16)' : `1px solid ${T.gray200}`,
    background: dark ? 'rgba(255,255,255,0.08)' : T.white,
    color: dark ? '#E5E7EB' : T.gray600,
    borderRadius: T.radiusXs,
    padding: '5px 9px',
    fontSize: 11,
    fontWeight: 800,
    cursor: 'pointer',
  };
}

function FilterPanel({
  category,
  setCategory,
}: {
  category: string;
  setCategory: (value: string) => void;
}) {
  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
      <PanelTitle icon={SlidersHorizontal} title="侦测范围" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        <CategoryChip name="全部" active={!category} onClick={() => setCategory('')} />
        {(CATEGORIES as readonly string[]).filter((item) => item !== '全部').map((item) => (
          <CategoryChip key={item} name={item} active={category === item} onClick={() => setCategory(category === item ? '' : item)} />
        ))}
      </div>
    </section>
  );
}

function SignalPanel({ items }: { items: ContentItem[] }) {
  const rows = [
    { label: '强突破', value: items.filter((item) => lfvScore(item) >= 40).length, color: T.primary },
    { label: '低权威源', value: items.filter((item) => sourceWeight(item) <= 35).length, color: T.teal },
    { label: '隐蔽高', value: items.filter((item) => obscureFactor(item) >= 0.6).length, color: T.amber },
  ];

  return (
    <section style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
      <PanelTitle icon={BarChart3} title="突破信号" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {rows.map((row) => (
          <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: row.color }} />
            <span style={{ flex: 1, fontSize: 12, color: T.gray600 }}>{row.label}</span>
            <span style={{ fontSize: 13, fontWeight: 900, color: T.gray900, fontFamily: T.mono }}>{row.value}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 13, paddingTop: 12, borderTop: `1px solid ${T.gray100}`, fontSize: 12, color: T.gray500, lineHeight: 1.7 }}>
        LFV 越高，说明内容在低权威来源中越可能完成了异常传播。
      </div>
    </section>
  );
}

function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (updater: number | ((page: number) => number)) => void;
}) {
  const pageNumbers = Array.from({ length: Math.min(5, totalPages) }, (_, index) => {
    if (totalPages <= 5) return index + 1;
    if (page <= 3) return index + 1;
    if (page >= totalPages - 2) return totalPages - 4 + index;
    return page - 2 + index;
  });

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 24 }}>
      <PageButton disabled={page === 1} onClick={() => onPage((current) => Math.max(1, current - 1))}>
        <ChevronLeft size={14} /> 上一页
      </PageButton>
      <div style={{ display: 'flex', gap: 5 }}>
        {pageNumbers.map((pageNumber) => (
          <button
            key={pageNumber}
            onClick={() => onPage(pageNumber)}
            style={{
              width: 32,
              height: 32,
              fontSize: 13,
              fontWeight: page === pageNumber ? 900 : 700,
              background: page === pageNumber ? T.primary : T.white,
              color: page === pageNumber ? T.white : T.gray600,
              border: `1px solid ${page === pageNumber ? T.primaryBorder : T.gray200}`,
              borderRadius: T.radiusSm,
              cursor: 'pointer',
            }}
          >
            {pageNumber}
          </button>
        ))}
      </div>
      <PageButton disabled={page === totalPages} onClick={() => onPage((current) => Math.min(totalPages, current + 1))}>
        下一页 <ChevronRight size={14} />
      </PageButton>
    </div>
  );
}

function PageButton({
  disabled,
  onClick,
  children,
}: {
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '8px 14px',
        fontSize: 13,
        fontWeight: 800,
        background: disabled ? T.gray50 : T.white,
        color: disabled ? T.gray300 : T.gray700,
        border: `1px solid ${T.gray200}`,
        borderRadius: T.radiusSm,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  );
}

function EmptyState() {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 80, textAlign: 'center', color: T.gray400 }}>
      <Inbox size={32} style={{ marginBottom: 10, opacity: 0.5 }} />
      <div style={{ fontSize: 15, fontWeight: 900, color: T.gray700 }}>暂无低粉爆文数据</div>
      <div style={{ marginTop: 6, fontSize: 12 }}>可以放宽时间窗口或分类范围。</div>
    </div>
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

function SignalPill({
  label,
  tone = 'muted',
  dark = false,
}: {
  label: string;
  tone?: 'good' | 'muted';
  dark?: boolean;
}) {
  return (
    <span style={{
      fontSize: 10,
      fontWeight: 800,
      color: dark ? '#CBD5E1' : tone === 'good' ? T.teal : T.gray500,
      background: dark ? 'rgba(255,255,255,0.08)' : tone === 'good' ? T.tealLight : T.gray100,
      border: dark ? '1px solid rgba(255,255,255,0.1)' : `1px solid ${tone === 'good' ? T.tealBorder : T.gray200}`,
      padding: '2px 7px',
      borderRadius: 999,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

function getAnalysis(item: ContentItem): ContentAnalysis | undefined {
  return item.analysis || item.analyses?.[0];
}

function lfvScore(item: ContentItem): number {
  const analysis = getAnalysis(item);
  return analysis?.adjusted_curation_score ?? analysis?.curation_score ?? 0;
}

function sourceWeight(item: ContentItem): number {
  return getAnalysis(item)?.score_breakdown?.dimension_scores?.source_weight ?? 0;
}

function obscureFactor(item: ContentItem): number {
  return getAnalysis(item)?.score_breakdown?.dimension_scores?.obscure_factor ?? 0;
}
