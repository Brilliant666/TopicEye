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
import { Button, Panel, Toolbar, cx } from '@/components/ui';
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

function chipStyle(active: boolean, color: string = '#111827'): React.CSSProperties {
  return {
    borderColor: active ? color : '#E5E7EB',
    background: active ? color : '#FFFFFF',
    color: active ? '#FFFFFF' : '#4B5563',
  };
}

function MetricPill({ children, color = '#6B7280', bg = '#F3F4F6' }: { children: React.ReactNode; color?: string; bg?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold" style={{ background: bg, color }}>
      {children}
    </span>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 p-9 text-gray-400">
      <RefreshCw size={16} className="fanqie-spin" />
      <span className="text-[13px]">{label}</span>
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
    <div className="p-12 text-center text-gray-400">
      <BookOpen size={28} strokeWidth={1.8} className="mx-auto" />
      <div className="mt-2.5 text-sm font-bold text-gray-500">{title}</div>
      <div className="mt-1 text-xs">{desc}</div>
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
          {item.is_over === 1 && <MetricPill color="#4B5563" bg="#F3F4F6"><CheckCircle2 size={12} />完结</MetricPill>}
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
    <article
      className={cx(
        'fanqie-book-card grid min-w-0 gap-[var(--fanqie-card-gap,16px)] rounded-sm border bg-white p-4 shadow-sm',
        isTop ? 'border-amber-border shadow-amber-100' : 'border-gray-200',
      )}
      style={{ gridTemplateColumns: 'var(--fanqie-card-cols, 44px 82px minmax(0, 1fr))' }}
    >
      <div className="flex flex-col items-center gap-1.5">
        <div className={cx('grid h-[34px] w-[34px] place-items-center rounded-sm font-mono text-base font-black', isTop ? 'bg-amber-light text-amber' : 'bg-gray-50 text-gray-400')}>
          {pos}
        </div>
        {typeof diff === 'number' && diff !== 0 && (
          <span className={cx('inline-flex items-center gap-0.5 font-mono text-[11px] font-extrabold', diff > 0 ? 'text-teal' : 'text-red')}>
            {diff > 0 ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
            {Math.abs(diff)}
          </span>
        )}
      </div>

      {coverSrc ? (
        <img
          src={coverSrc}
          alt={title}
          className="h-[var(--fanqie-cover-h,108px)] w-[var(--fanqie-cover-w,82px)] rounded-sm bg-gray-100 object-cover shadow-lg"
          onError={() => setCoverFailed(true)}
        />
      ) : (
        <div
          aria-label={`${title} 封面占位`}
          style={{
            width: 'var(--fanqie-cover-w, 82px)',
            height: 'var(--fanqie-cover-h, 108px)',
            background: `linear-gradient(160deg, ${platformMeta.bg}, #FAFAFA)`,
            color: platformMeta.color,
          }}
          className="grid place-items-center rounded-sm border border-gray-200 p-2 text-center text-[13px] font-black leading-tight shadow-md"
        >
          {title.slice(0, 2) || '书'}
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="m-0 truncate text-[17px] font-black leading-tight text-gray-900">{title}</h2>
            <div className="mt-1 text-xs text-gray-500">
              {author}{categoryText && <span className="text-gray-400"> · {categoryText}</span>}
            </div>
          </div>
          {itemUrl && (
            <a href={itemUrl} target="_blank" rel="noreferrer" title="打开官网原文" className="rounded-xs p-1 text-gray-400 transition hover:bg-gray-100 hover:text-primary">
              <ExternalLink size={16} />
            </a>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5">{meta}</div>

        {abstract && (
          <p className="line-clamp-3 m-0 text-xs leading-6 text-gray-500">
            {abstract}
          </p>
        )}

        {'latest_chapter_title' in item && item.latest_chapter_title && (
          <div className="truncate text-[11px] text-gray-400">更新 {item.latest_chapter_title}</div>
        )}
        {'last_chapter_title' in item && item.last_chapter_title && (
          <div className="truncate text-[11px] text-gray-400">更新 {item.last_chapter_title}</div>
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
    <div className="flex h-full flex-col overflow-hidden bg-page">
      <div className="shrink-0 border-b border-gray-200 bg-white px-7 pb-4 pt-[18px]">
        <div className="flex flex-wrap items-center gap-3.5">
          <div className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-md" style={{ background: platformMeta.bg, color: platformMeta.color }}>
            <Library size={22} strokeWidth={2.2} />
          </div>
          <div className="min-w-[220px]">
            <h1 className="m-0 text-[22px] font-black leading-tight text-gray-900">网文雷达</h1>
            <div className="mt-1 text-xs text-gray-500">{contextLabel}</div>
          </div>

          <div className="fanqie-platform-tabs flex gap-1.5 rounded-sm border border-gray-200 bg-gray-100 p-1">
            {(Object.keys(PLATFORM_META) as Platform[]).map((key) => {
              const meta = PLATFORM_META[key];
              const active = platform === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => { setPlatform(key); setQuery(''); }}
                  className={cx('flex min-w-28 cursor-pointer flex-col items-start gap-0.5 rounded-xs border-0 px-2.5 py-2 transition', active ? 'bg-white shadow-sm' : 'bg-transparent text-gray-500 hover:bg-white/60')}
                  style={{ color: active ? meta.color : undefined }}
                >
                  <span className="text-[13px] font-black">{meta.label}</span>
                  <span className={cx('text-[10px]', active ? 'text-gray-500' : 'text-gray-400')}>{meta.subtitle}</span>
                </button>
              );
            })}
          </div>

          <div className="flex-1" />
          <button
            type="button"
            onClick={handleSync}
            disabled={syncBusy}
            className="inline-flex items-center gap-2 rounded-sm border-0 px-3.5 py-2 text-[13px] font-extrabold text-white transition disabled:cursor-wait disabled:bg-gray-200"
            style={{ background: syncBusy ? undefined : platformMeta.color }}
          >
            <RefreshCw size={15} className={syncBusy ? 'fanqie-spin' : undefined} />
            {syncBusy ? '同步中' : `同步${platformMeta.label}`}
          </button>
        </div>
      </div>

      <div className="fanqie-layout grid min-h-0 flex-1 gap-4 p-[18px]">
        <aside className="fanqie-filter-panel flex min-h-0 flex-col gap-3 pr-0.5">
          <Panel className="p-4">
            <div className="mb-3 flex items-center gap-2">
              <Filter size={16} style={{ color: platformMeta.color }} />
              <div className="text-[13px] font-black text-gray-800">筛选控制台</div>
            </div>

            {platform === 'fanqie' && (
              <div className="flex flex-col gap-3.5">
                <FilterGroup title="频道">
                  {(Object.entries(GROUP_LABELS) as Array<[keyof typeof GROUP_LABELS, typeof GROUP_LABELS[keyof typeof GROUP_LABELS]]>).map(([key, value]) => (
                    <FilterChip key={key} active={groupTab === key} color={value.color} onClick={() => setGroupTab(key)}>{value.label}</FilterChip>
                  ))}
                </FilterGroup>
                <FilterGroup title="榜单">
                  {(Object.entries(RANK_TYPE_LABELS) as Array<[keyof typeof RANK_TYPE_LABELS, typeof RANK_TYPE_LABELS[keyof typeof RANK_TYPE_LABELS]]>).map(([key, value]) => (
                    <FilterChip key={key} active={rankTab === key} color={value.color} onClick={() => setRankTab(key)}>{value.label}</FilterChip>
                  ))}
                </FilterGroup>
                <FilterGroup title={`分类 · ${categories.filter((cat) => cat.group === groupTab).length}`}>
                  <div className="grid max-h-80 w-full grid-cols-2 gap-1.5 overflow-y-auto pr-1">
                    {categories.filter((cat) => cat.group === groupTab).map((cat) => (
                      <FilterChip
                        key={cat.fanqie_id}
                        title={cat.name}
                        active={activeCat === cat.fanqie_id}
                        color="#111827"
                        onClick={() => setActiveCat(cat.fanqie_id)}
                        className="min-h-8 w-full justify-center overflow-hidden px-2.5 py-2 text-center"
                      >
                        <span className="truncate">{cat.name}</span>
                      </FilterChip>
                    ))}
                  </div>
                </FilterGroup>
              </div>
            )}

            {platform === 'qimao' && (
              <div className="flex flex-col gap-3.5">
                <FilterGroup title="频道">
                  {(Object.entries(QIMAO_CHANNEL_LABELS) as Array<[keyof typeof QIMAO_CHANNEL_LABELS, typeof QIMAO_CHANNEL_LABELS[keyof typeof QIMAO_CHANNEL_LABELS]]>).map(([key, value]) => (
                    <FilterChip key={key} active={qimaoChannel === key} color={value.color} onClick={() => setQimaoChannel(key)}>{value.label}</FilterChip>
                  ))}
                </FilterGroup>
                <FilterGroup title="榜单">
                  {(Object.entries(QIMAO_RANK_LABELS) as Array<[keyof typeof QIMAO_RANK_LABELS, typeof QIMAO_RANK_LABELS[keyof typeof QIMAO_RANK_LABELS]]>).map(([key, value]) => (
                    <FilterChip key={key} active={qimaoRank === key} color={value.color} onClick={() => setQimaoRank(key)}>{value.label}</FilterChip>
                  ))}
                </FilterGroup>
              </div>
            )}

            {platform === 'zhihu' && (
              <div className="flex flex-col gap-3.5">
                <FilterGroup title="排序">
                  {(Object.entries(ZHIHU_SORT_LABELS) as Array<[keyof typeof ZHIHU_SORT_LABELS, typeof ZHIHU_SORT_LABELS[keyof typeof ZHIHU_SORT_LABELS]]>).map(([key, value]) => (
                    <FilterChip key={key} active={zhihuSort === key} color={value.color} onClick={() => setZhihuSort(key)}>{value.label}</FilterChip>
                  ))}
                </FilterGroup>
                <FilterGroup title="故事分类">
                  <div className="grid w-full grid-cols-2 gap-1.5">
                    {ZHIHU_SUBCATS.map((cat) => (
                      <FilterChip key={cat.key} active={zhihuSubcat === cat.key} color="#0066F5" onClick={() => setZhihuSubcat(cat.key)} className="min-w-0 justify-center">{cat.label}</FilterChip>
                    ))}
                  </div>
                </FilterGroup>
              </div>
            )}
          </Panel>

          <Panel className="p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] font-black text-gray-800">
              <Sparkles size={16} style={{ color: platformMeta.color }} />
              榜单摘要
            </div>
            <div className="grid grid-cols-2 gap-2">
              <SummaryTile label="当前条目" value={currentBooks.length} />
              <SummaryTile label="上升作品" value={risingCount} />
            </div>
            {topItem && (
              <div className="mt-3 rounded-sm p-3" style={{ background: platformMeta.bg, color: platformMeta.color }}>
                <div className="mb-1 flex items-center gap-1.5 text-[11px] font-black">
                  <Crown size={14} />
                  榜首
                </div>
                <div className="text-[13px] font-black leading-tight text-gray-900">{getItemTitle(topItem)}</div>
                <div className="mt-1 text-[11px] text-gray-600">{getItemAuthor(topItem)}</div>
              </div>
            )}
          </Panel>
        </aside>

        <main className="fanqie-main-panel flex min-h-0 flex-col gap-3">
          <Panel className="flex flex-wrap items-center gap-3 p-3.5">
            <div className="min-w-[220px] flex-1">
              <div className="flex items-center gap-2 text-xs font-black" style={{ color: platformMeta.color }}>
                <TrendingUp size={15} />
                {platformMeta.label}
              </div>
              <div className="mt-1 text-lg font-black text-gray-900">{contextLabel}</div>
              <div className="mt-1 text-xs text-gray-400">
                {query.trim() ? `筛出 ${filteredBooks.length} / ${currentBooks.length} 条` : `${currentBooks.length} 条榜单记录`}
              </div>
            </div>
            <div className="relative w-[280px] max-w-full">
              <Search size={15} className="absolute left-3 top-2.5 text-gray-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索书名、作者、简介"
                className="w-full rounded-sm border border-gray-200 py-2 pl-8 pr-9 text-[13px] text-gray-800 outline-none transition focus:border-primary"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  title="清空搜索"
                  className="absolute right-2 top-1.5 grid h-[26px] w-[26px] cursor-pointer place-items-center rounded-xs border-0 bg-gray-100 text-gray-500"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </Panel>

          {error && (
            <div className="rounded-sm border border-red-light bg-red-light px-3 py-2.5 text-[13px] text-red">{error}</div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
            {loading ? (
              <LoadingState label="正在拉取榜单" />
            ) : filteredBooks.length === 0 ? (
              query.trim() ? (
                <EmptyState title="没有匹配的作品" desc="换一个书名、作者或简介关键词试试。" />
              ) : (
                <EmptyState />
              )
            ) : (
              <div className="fanqie-book-grid grid gap-2.5">
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
      <div className="mb-2 text-[11px] font-extrabold text-gray-500">{title}</div>
      <div className="flex w-full flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function FilterChip({
  active,
  color,
  onClick,
  children,
  className,
  title,
}: {
  active: boolean;
  color: string;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cx('whitespace-nowrap rounded-xs border px-3 py-2 text-xs font-bold transition', className)}
      style={chipStyle(active, color)}
    >
      {children}
    </button>
  );
}

function SummaryTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-sm border border-gray-100 bg-gray-50 p-2.5">
      <div className="mb-1 text-[11px] text-gray-400">{label}</div>
      <div className="font-mono text-xl font-black text-gray-900">{value}</div>
    </div>
  );
}
