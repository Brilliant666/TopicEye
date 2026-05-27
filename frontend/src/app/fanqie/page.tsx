'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  Crown,
  ExternalLink,
  Filter,
  Flame,
  Library,
  RefreshCw,
  Search,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react';
import { T } from '@/lib/design-tokens';
import {
  fanqieApi,
  qimaoApi,
  zhihuApi,
  type FanqieCategory,
  type FanqieBook,
  type QimaoBook,
  type ZhihuAlbum,
} from '@/lib/api';

type Platform = 'fanqie' | 'qimao' | 'zhihu';
type BookItem = FanqieBook | QimaoBook | ZhihuAlbum;

const PLATFORM_META: Record<Platform, { label: string; subtitle: string; color: string; bg: string }> = {
  fanqie: { label: '番茄小说', subtitle: '免费网文热榜', color: '#DC2626', bg: '#FEF2F2' },
  qimao: { label: '七猫小说', subtitle: '付费与免费混合榜', color: '#2563EB', bg: '#EFF6FF' },
  zhihu: { label: '知乎盐选', subtitle: '故事与付费内容', color: '#0F766E', bg: '#ECFDF5' },
};

const GROUP_LABELS = {
  male: { label: '男频', color: '#2563EB', bg: '#EFF6FF' },
  female: { label: '女频', color: '#E11D48', bg: '#FFF1F2' },
} as const;

const RANK_TYPE_LABELS = {
  reading: { label: '阅读榜', color: '#059669', bg: '#ECFDF5' },
  new: { label: '新书榜', color: '#7C3AED', bg: '#F5F3FF' },
} as const;

const QIMAO_RANK_LABELS = {
  hot: { label: '大热', color: '#DC2626', bg: '#FEF2F2' },
  new: { label: '新书', color: '#7C3AED', bg: '#F5F3FF' },
  over: { label: '完结', color: '#D97706', bg: '#FFFBEB' },
  collect: { label: '收藏', color: '#2563EB', bg: '#EFF6FF' },
  update: { label: '更新', color: '#059669', bg: '#ECFDF5' },
} as const;

const QIMAO_CHANNEL_LABELS = {
  boy: { label: '男频', color: '#2563EB', bg: '#EFF6FF' },
  girl: { label: '女频', color: '#E11D48', bg: '#FFF1F2' },
} as const;

const ZHIHU_SORT_LABELS = {
  hottest: { label: '热门', color: '#DC2626', bg: '#FEF2F2' },
  newest: { label: '最新', color: '#7C3AED', bg: '#F5F3FF' },
  monthly_hottest: { label: '月热', color: '#D97706', bg: '#FFFBEB' },
} as const;

const ZHIHU_SUBCATS = [
  { key: '', label: '全部' },
  { key: '爱情', label: '爱情' },
  { key: '科幻', label: '科幻' },
  { key: '历史', label: '历史' },
  { key: '漫画', label: '漫画' },
  { key: '脑洞', label: '脑洞' },
  { key: '奇闻', label: '奇闻' },
  { key: '亲历', label: '亲历' },
  { key: '校园', label: '校园' },
  { key: '悬疑', label: '悬疑' },
];

function formatCount(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return String(n);
}

function getItemTitle(item: BookItem): string {
  if ('book_name' in item) return item.book_name;
  return item.title;
}

function getItemAuthor(item: BookItem): string {
  return item.author || '未知作者';
}

function getItemAbstract(item: BookItem): string {
  return (item.abstract || '').replace(/\n/g, ' ');
}

function getItemCover(item: BookItem): string | null {
  if ('thumb_url' in item) return item.thumb_url;
  return item.thumb_uri;
}

function getItemUrl(item: BookItem): string | null {
  if ('url' in item && item.url) return item.url;
  return null;
}

function getPositionChange(item: BookItem): number | null {
  if ('rank_pos_diff' in item && typeof item.rank_pos_diff === 'number') return item.rank_pos_diff;
  if ('index_change' in item && typeof item.index_change === 'number') return item.index_change;
  return null;
}

function chipStyle(active: boolean, color: string = T.gray900): React.CSSProperties {
  return {
    padding: '7px 11px',
    borderRadius: T.radiusXs,
    border: `1px solid ${active ? color : T.gray200}`,
    background: active ? color : T.white,
    color: active ? T.white : T.gray600,
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s, border-color 0.15s, color 0.15s',
  };
}

function MetricPill({ children, color = T.gray500, bg = T.gray100 }: { children: React.ReactNode; color?: string; bg?: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 7px', borderRadius: 999, background: bg, color, fontSize: 11, fontWeight: 700 }}>
      {children}
    </span>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div style={{ padding: 36, display: 'flex', justifyContent: 'center', alignItems: 'center', color: T.gray400, gap: 10 }}>
      <RefreshCw size={16} className="fanqie-spin" />
      <span style={{ fontSize: 13 }}>{label}</span>
    </div>
  );
}

function EmptyState({
  title = '暂无榜单数据',
  desc = '可以先同步当前平台，或切换榜单筛选。',
}: {
  title?: string;
  desc?: string;
}) {
  return (
    <div style={{ padding: 48, textAlign: 'center', color: T.gray400 }}>
      <BookOpen size={28} strokeWidth={1.8} />
      <div style={{ marginTop: 10, fontSize: 14, fontWeight: 700, color: T.gray500 }}>{title}</div>
      <div style={{ marginTop: 4, fontSize: 12 }}>{desc}</div>
    </div>
  );
}

function BookCard({ item, platform, rankTab }: { item: BookItem; platform: Platform; rankTab: string }) {
  const [coverFailed, setCoverFailed] = useState(false);
  const pos = item.position;
  const title = getItemTitle(item);
  const author = getItemAuthor(item);
  const cover = getItemCover(item);
  const coverSrc = cover && !coverFailed ? cover : null;
  const abstract = getItemAbstract(item);
  const itemUrl = getItemUrl(item);
  const diff = getPositionChange(item);
  const isTop = pos <= 3;
  const platformMeta = PLATFORM_META[platform];

  useEffect(() => {
    setCoverFailed(false);
  }, [cover]);

  const meta = (() => {
    if (platform === 'fanqie' && 'read_count' in item) {
      const rankInfo = RANK_TYPE_LABELS[rankTab as keyof typeof RANK_TYPE_LABELS];
      return (
        <>
          <MetricPill color={rankInfo?.color} bg={rankInfo?.bg}>{rankInfo?.label || '榜单'}</MetricPill>
          <MetricPill>{formatCount(item.read_count)}阅读</MetricPill>
          <MetricPill>{formatCount(item.word_number)}字</MetricPill>
        </>
      );
    }
    if (platform === 'qimao' && 'collect_count' in item) {
      return (
        <>
          {item.is_continue_top === 1 && <MetricPill color="#D97706" bg="#FFFBEB"><Crown size={12} />霸榜</MetricPill>}
          {item.is_over === 1 && <MetricPill color={T.gray600} bg={T.gray100}><CheckCircle2 size={12} />完结</MetricPill>}
          <MetricPill color="#DC2626" bg="#FEF2F2">{formatCount(item.collect_count)}收藏</MetricPill>
          <MetricPill>{item.words_num}</MetricPill>
        </>
      );
    }
    if (platform === 'zhihu' && 'price_yuan' in item) {
      const sortInfo = ZHIHU_SORT_LABELS[item.sort_type as keyof typeof ZHIHU_SORT_LABELS] || ZHIHU_SORT_LABELS.hottest;
      return (
        <>
          <MetricPill color={sortInfo.color} bg={sortInfo.bg}>{sortInfo.label}</MetricPill>
          {item.is_exclusive && <MetricPill color="#D97706" bg="#FFFBEB">独家</MetricPill>}
          {item.tag === '会员专享' && <MetricPill color="#2563EB" bg="#EFF6FF">会员</MetricPill>}
          {item.chapter_text && <MetricPill>{item.chapter_text}</MetricPill>}
          {item.price_yuan && item.price_yuan !== '免费' && <MetricPill color="#DC2626" bg="#FEF2F2">{item.price_yuan}</MetricPill>}
        </>
      );
    }
    return null;
  })();

  const categoryText = (() => {
    if ('category1_name' in item && item.category1_name) {
      return [item.category1_name, item.category2_name].filter(Boolean).join(' · ');
    }
    return '';
  })();

  return (
    <article className="fanqie-book-card" style={{
      display: 'grid',
      gridTemplateColumns: 'var(--fanqie-card-cols, 44px 82px minmax(0, 1fr))',
      gap: 'var(--fanqie-card-gap, 16px)',
      padding: 16,
      background: T.white,
      border: `1px solid ${isTop ? '#FCD34D' : T.gray200}`,
      borderRadius: T.radiusSm,
      boxShadow: isTop ? '0 8px 22px rgba(245, 158, 11, 0.12)' : '0 1px 2px rgba(15, 23, 42, 0.04)',
      minWidth: 0,
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
        <div style={{
          width: 34,
          height: 34,
          borderRadius: 8,
          display: 'grid',
          placeItems: 'center',
          background: isTop ? '#FFFBEB' : T.gray50,
          color: isTop ? '#B45309' : T.gray400,
          fontSize: 16,
          fontWeight: 900,
          fontFamily: T.mono,
        }}>
          {pos}
        </div>
        {typeof diff === 'number' && diff !== 0 && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, color: diff > 0 ? '#059669' : '#DC2626', fontSize: 11, fontWeight: 800, fontFamily: T.mono }}>
            {diff > 0 ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
            {Math.abs(diff)}
          </span>
        )}
      </div>

      {coverSrc ? (
        <img
          src={coverSrc}
          alt={title}
          style={{
            width: 'var(--fanqie-cover-w, 82px)',
            height: 'var(--fanqie-cover-h, 108px)',
            objectFit: 'cover',
            borderRadius: 8,
            background: T.gray100,
            boxShadow: '0 8px 18px rgba(15, 23, 42, 0.14)',
          }}
          onError={() => setCoverFailed(true)}
        />
      ) : (
        <div
          aria-label={`${title} 封面占位`}
          style={{
            width: 'var(--fanqie-cover-w, 82px)',
            height: 'var(--fanqie-cover-h, 108px)',
            borderRadius: 8,
            background: `linear-gradient(160deg, ${platformMeta.bg}, ${T.gray50})`,
            border: `1px solid ${T.gray200}`,
            color: platformMeta.color,
            display: 'grid',
            placeItems: 'center',
            textAlign: 'center',
            padding: 8,
            fontSize: 13,
            lineHeight: 1.25,
            fontWeight: 900,
            boxShadow: '0 8px 18px rgba(15, 23, 42, 0.08)',
          }}
        >
          {title.slice(0, 2) || '书'}
        </div>
      )}

      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2 style={{ margin: 0, color: T.gray900, fontSize: 17, lineHeight: 1.35, fontWeight: 850, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</h2>
            <div style={{ marginTop: 3, color: T.gray500, fontSize: 12 }}>
              {author}{categoryText && <span style={{ color: T.gray400 }}> · {categoryText}</span>}
            </div>
          </div>
          {itemUrl && (
            <a href={itemUrl} target="_blank" rel="noreferrer" title="打开官网原文" style={{ color: T.gray400, padding: 4, borderRadius: 6 }}>
              <ExternalLink size={16} />
            </a>
          )}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{meta}</div>

        {abstract && (
          <p style={{ margin: 0, color: T.gray500, fontSize: 12, lineHeight: 1.65, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {abstract}
          </p>
        )}

        {'latest_chapter_title' in item && item.latest_chapter_title && (
          <div style={{ color: T.gray400, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>更新 {item.latest_chapter_title}</div>
        )}
        {'last_chapter_title' in item && item.last_chapter_title && (
          <div style={{ color: T.gray400, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>更新 {item.last_chapter_title}</div>
        )}
      </div>
    </article>
  );
}

export default function FanqiePage() {
  const [platform, setPlatform] = useState<Platform>('fanqie');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);

  const [categories, setCategories] = useState<FanqieCategory[]>([]);
  const [booksMap, setBooksMap] = useState<Record<string, FanqieBook[]>>({});
  const [initLoading, setInitLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [rankTab, setRankTab] = useState<'new' | 'reading'>('reading');
  const [activeCat, setActiveCat] = useState('');
  const [groupTab, setGroupTab] = useState<'male' | 'female'>('male');

  const [qimaoBooks, setQimaoBooks] = useState<QimaoBook[]>([]);
  const [qimaoLoading, setQimaoLoading] = useState(false);
  const [qimaoSyncing, setQimaoSyncing] = useState(false);
  const [qimaoChannel, setQimaoChannel] = useState<'boy' | 'girl'>('boy');
  const [qimaoRank, setQimaoRank] = useState<keyof typeof QIMAO_RANK_LABELS>('hot');

  const [zhihuAlbums, setZhihuAlbums] = useState<ZhihuAlbum[]>([]);
  const [zhihuLoading, setZhihuLoading] = useState(false);
  const [zhihuSyncing, setZhihuSyncing] = useState(false);
  const [zhihuSort, setZhihuSort] = useState<keyof typeof ZHIHU_SORT_LABELS>('hottest');
  const [zhihuSubcat, setZhihuSubcat] = useState('');

  const fetchFanqieData = useCallback(async (rt: string, isInit = false) => {
    if (isInit) setInitLoading(true); else setSwitching(true);
    setError(null);
    try {
      const cats = categories.length ? categories : await fanqieApi.categories();
      if (isInit || categories.length === 0) setCategories(cats);

      const fallbackCat = cats.find((cat) => cat.group === groupTab)?.fanqie_id || cats[0]?.fanqie_id || '';
      const catId = activeCat || fallbackCat;
      if (!activeCat && catId) setActiveCat(catId);

      if (catId) {
        const result = await fanqieApi.categoryBooks(catId, { rank_type: rt });
        setBooksMap((prev) => ({ ...prev, [`${catId}|${rt}`]: result.books }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '番茄榜单加载失败');
    } finally {
      setInitLoading(false);
      setSwitching(false);
    }
  }, [activeCat, categories, groupTab]);

  const fetchQimaoData = useCallback(async () => {
    setQimaoLoading(true);
    setError(null);
    try {
      const result = await qimaoApi.list(qimaoChannel, qimaoRank);
      setQimaoBooks(result.books);
    } catch (err) {
      setError(err instanceof Error ? err.message : '七猫榜单加载失败');
    } finally {
      setQimaoLoading(false);
    }
  }, [qimaoChannel, qimaoRank]);

  const fetchZhihuData = useCallback(async () => {
    setZhihuLoading(true);
    setError(null);
    try {
      const result = await zhihuApi.list(zhihuSort, '故事', zhihuSubcat || undefined);
      setZhihuAlbums(result.albums);
    } catch (err) {
      setError(err instanceof Error ? err.message : '知乎盐选加载失败');
    } finally {
      setZhihuLoading(false);
    }
  }, [zhihuSort, zhihuSubcat]);

  useEffect(() => {
    if (platform === 'fanqie') void fetchFanqieData(rankTab, true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (platform !== 'fanqie' || categories.length === 0) return;
    const first = categories.find((cat) => cat.group === groupTab);
    if (first && first.fanqie_id !== activeCat) {
      setActiveCat(first.fanqie_id);
      setBooksMap({});
    }
  }, [groupTab, categories]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (platform === 'fanqie') void fetchFanqieData(rankTab);
  }, [platform, rankTab, activeCat]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (platform === 'qimao') void fetchQimaoData();
  }, [platform, qimaoChannel, qimaoRank, fetchQimaoData]);

  useEffect(() => {
    if (platform === 'zhihu') void fetchZhihuData();
  }, [platform, zhihuSort, zhihuSubcat, fetchZhihuData]);

  const fanqieBooks = useMemo(() => booksMap[`${activeCat}|${rankTab}`] || [], [activeCat, booksMap, rankTab]);
  const currentBooks: BookItem[] = platform === 'fanqie' ? fanqieBooks : platform === 'qimao' ? qimaoBooks : zhihuAlbums;
  const loading = platform === 'fanqie' ? initLoading || switching : platform === 'qimao' ? qimaoLoading : zhihuLoading;
  const platformMeta = PLATFORM_META[platform];
  const currentCategory = categories.find((cat) => cat.fanqie_id === activeCat);

  const filteredBooks = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return currentBooks;
    return currentBooks.filter((item) => {
      const haystack = [getItemTitle(item), getItemAuthor(item), getItemAbstract(item)].join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [currentBooks, query]);

  const risingCount = currentBooks.filter((item) => (getPositionChange(item) || 0) > 0).length;
  const topItem = currentBooks[0];
  const contextLabel = platform === 'fanqie'
    ? `${GROUP_LABELS[groupTab].label} · ${RANK_TYPE_LABELS[rankTab].label}${currentCategory ? ` · ${currentCategory.name}` : ''}`
    : platform === 'qimao'
      ? `${QIMAO_CHANNEL_LABELS[qimaoChannel].label} · ${QIMAO_RANK_LABELS[qimaoRank].label}`
      : `故事 · ${ZHIHU_SORT_LABELS[zhihuSort].label}${zhihuSubcat ? ` · ${zhihuSubcat}` : ''}`;

  const handleSync = async () => {
    if (platform === 'fanqie') {
      setSyncing(true);
      try {
        await fanqieApi.sync();
        await fetchFanqieData(rankTab, true);
      } catch (err) {
        setError(err instanceof Error ? err.message : '番茄同步失败');
      } finally {
        setSyncing(false);
      }
      return;
    }
    if (platform === 'qimao') {
      setQimaoSyncing(true);
      try {
        await qimaoApi.sync();
        await fetchQimaoData();
      } catch (err) {
        setError(err instanceof Error ? err.message : '七猫同步失败');
      } finally {
        setQimaoSyncing(false);
      }
      return;
    }
    setZhihuSyncing(true);
    try {
      await zhihuApi.sync();
      await fetchZhihuData();
    } catch (err) {
      setError(err instanceof Error ? err.message : '知乎同步失败');
    } finally {
      setZhihuSyncing(false);
    }
  };

  const syncBusy = syncing || qimaoSyncing || zhihuSyncing;

  return (
    <div style={{ height: '100%', overflow: 'hidden', background: T.bg, display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: T.white, borderBottom: `1px solid ${T.gray200}`, padding: '18px 28px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: platformMeta.bg, color: platformMeta.color, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
            <Library size={22} strokeWidth={2.2} />
          </div>
          <div style={{ minWidth: 220 }}>
            <h1 style={{ margin: 0, color: T.gray900, fontSize: 22, lineHeight: 1.15, fontWeight: 900 }}>网文雷达</h1>
            <div style={{ marginTop: 4, color: T.gray500, fontSize: 12 }}>{contextLabel}</div>
          </div>

          <div className="fanqie-platform-tabs" style={{ display: 'flex', gap: 6, padding: 3, background: T.gray100, borderRadius: T.radiusSm, border: `1px solid ${T.gray200}` }}>
            {(Object.keys(PLATFORM_META) as Platform[]).map((key) => {
              const meta = PLATFORM_META[key];
              const active = platform === key;
              return (
                <button key={key} onClick={() => { setPlatform(key); setQuery(''); }} style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 2,
                  minWidth: 112, padding: '8px 10px', border: 'none', borderRadius: T.radiusXs,
                  background: active ? T.white : 'transparent', color: active ? meta.color : T.gray500,
                  cursor: 'pointer', boxShadow: active ? '0 1px 3px rgba(15, 23, 42, 0.1)' : 'none',
                }}>
                  <span style={{ fontSize: 13, fontWeight: 850 }}>{meta.label}</span>
                  <span style={{ fontSize: 10, color: active ? T.gray500 : T.gray400 }}>{meta.subtitle}</span>
                </button>
              );
            })}
          </div>

          <div style={{ flex: 1 }} />
          <button onClick={handleSync} disabled={syncBusy} style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '9px 14px', border: 'none', borderRadius: T.radiusSm,
            background: syncBusy ? T.gray200 : platformMeta.color, color: T.white,
            fontSize: 13, fontWeight: 800, cursor: syncBusy ? 'wait' : 'pointer',
          }}>
            <RefreshCw size={15} className={syncBusy ? 'fanqie-spin' : undefined} />
            {syncBusy ? '同步中' : `同步${platformMeta.label}`}
          </button>
        </div>
      </div>

      <div className="fanqie-layout" style={{ flex: 1, minHeight: 0, display: 'grid', gap: 16, padding: 18 }}>
        <aside className="fanqie-filter-panel" style={{ minHeight: 0, paddingRight: 2, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Filter size={16} color={platformMeta.color} />
              <div style={{ fontSize: 13, fontWeight: 850, color: T.gray800 }}>筛选控制台</div>
            </div>

            {platform === 'fanqie' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <FilterGroup title="频道">
                  {(Object.entries(GROUP_LABELS) as Array<[keyof typeof GROUP_LABELS, typeof GROUP_LABELS[keyof typeof GROUP_LABELS]]>).map(([key, value]) => (
                    <button key={key} onClick={() => setGroupTab(key)} style={chipStyle(groupTab === key, value.color)}>{value.label}</button>
                  ))}
                </FilterGroup>
                <FilterGroup title="榜单">
                  {(Object.entries(RANK_TYPE_LABELS) as Array<[keyof typeof RANK_TYPE_LABELS, typeof RANK_TYPE_LABELS[keyof typeof RANK_TYPE_LABELS]]>).map(([key, value]) => (
                    <button key={key} onClick={() => setRankTab(key)} style={chipStyle(rankTab === key, value.color)}>{value.label}</button>
                  ))}
                </FilterGroup>
                <FilterGroup title={`分类 · ${categories.filter((cat) => cat.group === groupTab).length}`}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6, maxHeight: 320, overflowY: 'auto', paddingRight: 4, width: '100%' }}>
                    {categories.filter((cat) => cat.group === groupTab).map((cat) => (
                      <button
                        key={cat.fanqie_id}
                        title={cat.name}
                        onClick={() => setActiveCat(cat.fanqie_id)}
                        style={{
                          ...chipStyle(activeCat === cat.fanqie_id, T.gray900),
                          width: '100%',
                          minHeight: 32,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          padding: '8px 10px',
                          overflow: 'hidden',
                          textAlign: 'center',
                          minWidth: 0,
                        }}
                      >
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{cat.name}</span>
                      </button>
                    ))}
                  </div>
                </FilterGroup>
              </div>
            )}

            {platform === 'qimao' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <FilterGroup title="频道">
                  {(Object.entries(QIMAO_CHANNEL_LABELS) as Array<[keyof typeof QIMAO_CHANNEL_LABELS, typeof QIMAO_CHANNEL_LABELS[keyof typeof QIMAO_CHANNEL_LABELS]]>).map(([key, value]) => (
                    <button key={key} onClick={() => setQimaoChannel(key)} style={chipStyle(qimaoChannel === key, value.color)}>{value.label}</button>
                  ))}
                </FilterGroup>
                <FilterGroup title="榜单">
                  {(Object.entries(QIMAO_RANK_LABELS) as Array<[keyof typeof QIMAO_RANK_LABELS, typeof QIMAO_RANK_LABELS[keyof typeof QIMAO_RANK_LABELS]]>).map(([key, value]) => (
                    <button key={key} onClick={() => setQimaoRank(key)} style={chipStyle(qimaoRank === key, value.color)}>{value.label}</button>
                  ))}
                </FilterGroup>
              </div>
            )}

            {platform === 'zhihu' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <FilterGroup title="排序">
                  {(Object.entries(ZHIHU_SORT_LABELS) as Array<[keyof typeof ZHIHU_SORT_LABELS, typeof ZHIHU_SORT_LABELS[keyof typeof ZHIHU_SORT_LABELS]]>).map(([key, value]) => (
                    <button key={key} onClick={() => setZhihuSort(key)} style={chipStyle(zhihuSort === key, value.color)}>{value.label}</button>
                  ))}
                </FilterGroup>
                <FilterGroup title="故事分类">
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, width: '100%' }}>
                    {ZHIHU_SUBCATS.map((cat) => (
                      <button key={cat.key} onClick={() => setZhihuSubcat(cat.key)} style={{ ...chipStyle(zhihuSubcat === cat.key, '#0066F5'), minWidth: 0 }}>{cat.label}</button>
                    ))}
                  </div>
                </FilterGroup>
              </div>
            )}
          </div>

          <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: T.gray800, fontSize: 13, fontWeight: 850, marginBottom: 12 }}>
              <Sparkles size={16} color={platformMeta.color} />
              榜单摘要
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <SummaryTile label="当前条目" value={currentBooks.length} />
              <SummaryTile label="上升作品" value={risingCount} />
            </div>
            {topItem && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: T.radiusSm, background: platformMeta.bg, color: platformMeta.color }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 900, marginBottom: 5 }}>
                  <Crown size={14} />
                  榜首
                </div>
                <div style={{ color: T.gray900, fontSize: 13, fontWeight: 850, lineHeight: 1.35 }}>{getItemTitle(topItem)}</div>
                <div style={{ marginTop: 4, color: T.gray600, fontSize: 11 }}>{getItemAuthor(topItem)}</div>
              </div>
            )}
          </div>
        </aside>

        <main className="fanqie-main-panel" style={{ minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 14, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 220, flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: platformMeta.color, fontSize: 12, fontWeight: 900 }}>
                <TrendingUp size={15} />
                {platformMeta.label}
              </div>
              <div style={{ marginTop: 3, color: T.gray900, fontSize: 18, fontWeight: 900 }}>{contextLabel}</div>
              <div style={{ marginTop: 4, color: T.gray400, fontSize: 12 }}>
                {query.trim() ? `筛出 ${filteredBooks.length} / ${currentBooks.length} 条` : `${currentBooks.length} 条榜单记录`}
              </div>
            </div>
            <div style={{ position: 'relative', width: 280, maxWidth: '100%' }}>
              <Search size={15} color={T.gray400} style={{ position: 'absolute', left: 11, top: 10 }} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索书名、作者、简介"
                style={{
                  width: '100%',
                  padding: '9px 36px 9px 34px',
                  border: `1px solid ${T.gray200}`,
                  borderRadius: T.radiusSm,
                  outline: 'none',
                  color: T.gray800,
                  fontSize: 13,
                }}
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  title="清空搜索"
                  style={{
                    position: 'absolute',
                    right: 8,
                    top: 7,
                    width: 26,
                    height: 26,
                    border: 'none',
                    borderRadius: 6,
                    background: T.gray100,
                    color: T.gray500,
                    display: 'grid',
                    placeItems: 'center',
                    cursor: 'pointer',
                  }}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          {error && (
            <div style={{ background: T.redLight, color: T.red, borderRadius: T.radiusSm, padding: '10px 12px', fontSize: 13, border: `1px solid ${T.redLight}` }}>{error}</div>
          )}

          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: 2 }}>
            {loading ? (
              <LoadingState label="正在拉取榜单" />
            ) : filteredBooks.length === 0 ? (
              query.trim() ? (
                <EmptyState title="没有匹配的作品" desc="换一个书名、作者或简介关键词试试。" />
              ) : (
                <EmptyState />
              )
            ) : (
              <div className="fanqie-book-grid" style={{ display: 'grid', gap: 10 }}>
                {filteredBooks.map((item) => (
                  <BookCard
                    key={'book_id' in item ? `${platform}-${item.book_id}-${item.position}` : `${platform}-${item.business_id}-${item.position}`}
                    item={item}
                    platform={platform}
                    rankTab={rankTab}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ color: T.gray500, fontSize: 11, fontWeight: 800, marginBottom: 7 }}>{title}</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', width: '100%' }}>{children}</div>
    </div>
  );
}

function SummaryTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ padding: 10, borderRadius: T.radiusSm, background: T.gray50, border: `1px solid ${T.gray100}` }}>
      <div style={{ color: T.gray400, fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color: T.gray900, fontFamily: T.mono, fontSize: 20, fontWeight: 900 }}>{value}</div>
    </div>
  );
}
