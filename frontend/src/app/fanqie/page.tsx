'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';
import { fanqieApi, type FanqieCategory, type FanqieBook } from '@/lib/api';

/* ── Constants ── */

const GROUP_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  male: { label: '男频', color: '#2563EB', bg: '#EFF6FF' },
  female: { label: '女频', color: '#E11D48', bg: '#FFF1F2' },
};

const RANK_TYPE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  male_new: { label: '男频新书', color: '#2563EB', bg: '#EFF6FF' },
  male_reading: { label: '男频阅读', color: '#1D4ED8', bg: '#DBEAFE' },
  female_new: { label: '女频新书', color: '#E11D48', bg: '#FFF1F2' },
  female_reading: { label: '女频阅读', color: '#BE123C', bg: '#FFE4E6' },
};

const TABS = [
  { key: 'all', label: '全部分类' },
  { key: 'male', label: '男频' },
  { key: 'female', label: '女频' },
] as const;

/* ── Helper ── */

function formatReadCount(raw: string): string {
  const n = parseInt(raw, 10);
  if (isNaN(n)) return raw;
  if (n >= 100000000) return (n / 100000000).toFixed(1) + '亿';
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString();
}

function formatWordCount(raw: string): string {
  const n = parseInt(raw, 10);
  if (isNaN(n)) return raw;
  if (n >= 10000) return (n / 10000).toFixed(1) + '万字';
  return n.toLocaleString() + '字';
}

/* ── Components ── */

function RankBadge({ rank }: { rank: number }) {
  const isTop3 = rank <= 3;
  return (
    <div style={{
      width: 26, height: 26, borderRadius: '50%',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 700, flexShrink: 0,
      fontFamily: T.mono,
      ...(isTop3
        ? { background: rank === 1 ? '#FF6B35' : rank === 2 ? '#FF8F65' : '#FFB899', color: '#fff' }
        : { background: T.gray100, color: T.gray500 }),
    }}>
      {rank}
    </div>
  );
}

function BookCard({ book, rank }: { book: FanqieBook; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const rankInfo = RANK_TYPE_LABELS[book.rank_type];

  return (
    <div style={{
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      overflow: 'hidden',
      transition: 'box-shadow 0.15s ease',
      background: T.white,
    }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: '12px 14px',
          cursor: 'pointer',
          display: 'flex',
          gap: 12,
          alignItems: 'flex-start',
        }}
      >
        {/* 排名 */}
        <RankBadge rank={rank} />

        {/* 封面 */}
        {book.thumb_uri && (
          <img
            src={book.thumb_uri}
            alt={book.book_name}
            style={{
              width: 44, height: 60, borderRadius: 4,
              objectFit: 'cover', flexShrink: 0,
              border: `1px solid ${T.gray200}`,
            }}
          />
        )}

        {/* 信息 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 14, fontWeight: 600, color: T.gray900,
            overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {book.book_name}
          </div>
          <div style={{
            fontSize: 11, color: T.gray500, marginTop: 3,
            overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {book.author}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
            {/* 榜单类型标签 */}
            {rankInfo && (
              <span style={{
                fontSize: 9, fontWeight: 600, padding: '1px 6px',
                borderRadius: 4, background: rankInfo.bg, color: rankInfo.color,
              }}>
                {rankInfo.label}
              </span>
            )}
            {/* 阅读量 */}
            {book.read_count && (
              <span style={{
                fontSize: 10, color: T.gray400, fontFamily: T.mono,
              }}>
                {formatReadCount(book.read_count)}阅读
              </span>
            )}
            {/* 字数 */}
            {book.word_number && (
              <span style={{
                fontSize: 10, color: T.gray400, fontFamily: T.mono,
              }}>
                {formatWordCount(book.word_number)}
              </span>
            )}
          </div>
        </div>

        {/* 展开指示 */}
        <span style={{ fontSize: 11, color: T.gray400, flexShrink: 0, paddingTop: 2 }}>
          {expanded ? '收起↑' : '展开↓'}
        </span>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div style={{
          padding: '0 14px 14px',
          borderTop: `1px solid ${T.gray100}`,
          paddingTop: 10,
        }}>
          {/* 简介 */}
          {book.abstract && (
            <div style={{
              fontSize: 12, color: T.gray600, lineHeight: 1.6,
              maxHeight: 120, overflow: 'auto',
              background: T.gray50,
              padding: '8px 10px',
              borderRadius: T.radiusXs,
            }}>
              {book.abstract}
            </div>
          )}
          {/* 最新章节 */}
          {book.last_chapter_title && (
            <div style={{
              fontSize: 11, color: T.gray400, marginTop: 8,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <span style={{
                fontSize: 9, fontWeight: 600, padding: '1px 5px',
                borderRadius: 4, background: T.tealLight, color: T.teal,
              }}>
                最新
              </span>
              {book.last_chapter_title}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CategorySection({
  category,
  books,
}: {
  category: FanqieCategory;
  books: FanqieBook[];
}) {
  const [showAll, setShowAll] = useState(false);
  const groupInfo = GROUP_LABELS[category.group] || GROUP_LABELS.male;
  const displayBooks = showAll ? books : books.slice(0, 5);

  if (books.length === 0) return null;

  return (
    <div style={{ marginBottom: 20 }}>
      {/* 分类标题 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 10,
      }}>
        <span style={{
          fontSize: 15, fontWeight: 700, color: T.gray900,
        }}>
          {category.name}
        </span>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '2px 7px',
          borderRadius: 6, background: groupInfo.bg, color: groupInfo.color,
        }}>
          {groupInfo.label}
        </span>
        <span style={{
          fontSize: 11, color: T.gray400, fontFamily: T.mono,
        }}>
          {books.length}本
        </span>
      </div>

      {/* 图书列表 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {displayBooks.map((book, i) => (
          <BookCard key={`${book.book_id}-${book.rank_type}`} book={book} rank={i + 1} />
        ))}
      </div>

      {/* 展开/收起 */}
      {books.length > 5 && (
        <button
          onClick={() => setShowAll(!showAll)}
          style={{
            marginTop: 8, fontSize: 12, fontWeight: 500,
            color: T.primary, background: 'none',
            border: 'none', cursor: 'pointer',
            padding: '4px 0',
          }}
        >
          {showAll ? '收起' : `查看全部 ${books.length} 本 ↓`}
        </button>
      )}
    </div>
  );
}

/* ── Stats Bar ── */

function StatsBar({ categories, totalBooks }: { categories: FanqieCategory[]; totalBooks: number }) {
  const maleCount = categories.filter(c => c.group === 'male').length;
  const femaleCount = categories.filter(c => c.group === 'female').length;

  return (
    <div style={{
      display: 'flex', gap: 12, marginBottom: 20,
    }}>
      {[
        { label: '分类总数', value: categories.length, color: T.primary },
        { label: '男频分类', value: maleCount, color: '#2563EB' },
        { label: '女频分类', value: femaleCount, color: '#E11D48' },
        { label: '图书总量', value: totalBooks, color: T.teal },
      ].map(stat => (
        <div key={stat.label} style={{
          padding: '12px 16px',
          background: T.white,
          border: `1px solid ${T.gray200}`,
          borderRadius: T.radius,
          flex: 1,
          textAlign: 'center',
        }}>
          <div style={{
            fontSize: 22, fontWeight: 800, color: stat.color,
            fontFamily: T.mono,
          }}>
            {stat.value}
          </div>
          <div style={{ fontSize: 11, color: T.gray500, marginTop: 2 }}>
            {stat.label}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Page ── */

export default function FanqiePage() {
  const [categories, setCategories] = useState<FanqieCategory[]>([]);
  const [booksMap, setBooksMap] = useState<Record<string, FanqieBook[]>>({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [tab, setTab] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const cats = await fanqieApi.categories();
      setCategories(cats);

      // 按分类批量加载图书
      const map: Record<string, FanqieBook[]> = {};
      for (const cat of cats) {
        try {
          const result = await fanqieApi.categoryBooks(cat.fanqie_id, { limit: 100 });
          map[cat.fanqie_id] = result.books || [];
        } catch {
          map[cat.fanqie_id] = [];
        }
      }
      setBooksMap(map);
    } catch (e) {
      console.error('Failed to load fanqie data:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fanqieApi.sync();
      await fetchData();
    } catch (e) {
      console.error('Sync failed:', e);
    } finally {
      setSyncing(false);
    }
  };

  // 过滤分类
  const filteredCategories = selectedCategory
    ? categories.filter(c => c.fanqie_id === selectedCategory)
    : tab === 'all'
      ? categories
      : categories.filter(c => c.group === tab);

  const totalBooks = Object.values(booksMap).reduce((sum, books) => sum + books.length, 0);

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900 }}>
      {/* 页面头部 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: T.gray900, margin: 0 }}>
            网文雷达
          </h1>
          <p style={{ fontSize: 13, color: T.gray500, marginTop: 4 }}>
            番茄小说分类榜单追踪 · 每日凌晨自动更新
          </p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          style={{
            fontSize: 12, fontWeight: 600,
            padding: '8px 18px', borderRadius: T.radiusSm,
            background: syncing ? T.gray300 : T.primary,
            color: T.white,
            border: 'none', cursor: syncing ? 'not-allowed' : 'pointer',
            transition: 'background 0.15s ease',
          }}
        >
          {syncing ? '同步中...' : '立即同步'}
        </button>
      </div>

      {/* 统计卡片 */}
      {!loading && <StatsBar categories={categories} totalBooks={totalBooks} />}

      {/* Tab 切换 + 分类选择 */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 20,
        flexWrap: 'wrap',
      }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setSelectedCategory(null); }}
            style={{
              fontSize: 12, fontWeight: 600,
              padding: '6px 14px', borderRadius: 20,
              background: tab === t.key && !selectedCategory ? T.primary : T.gray100,
              color: tab === t.key && !selectedCategory ? T.white : T.gray600,
              border: 'none', cursor: 'pointer',
              transition: 'all 0.12s ease',
            }}
          >
            {t.label}
          </button>
        ))}
        {/* 具体分类快捷选择 */}
        <span style={{ width: 1, background: T.gray200, margin: '0 4px' }} />
        {categories
          .filter(c => tab === 'all' || c.group === tab)
          .slice(0, 10)
          .map(cat => (
            <button
              key={cat.fanqie_id}
              onClick={() => setSelectedCategory(
                selectedCategory === cat.fanqie_id ? null : cat.fanqie_id
              )}
              style={{
                fontSize: 11, fontWeight: 500,
                padding: '4px 10px', borderRadius: 14,
                background: selectedCategory === cat.fanqie_id ? T.teal : T.gray100,
                color: selectedCategory === cat.fanqie_id ? T.white : T.gray600,
                border: 'none', cursor: 'pointer',
                transition: 'all 0.12s ease',
                whiteSpace: 'nowrap',
              }}
            >
              {cat.name}
            </button>
          ))}
      </div>

      {/* 加载状态 */}
      {loading && (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          fontSize: 14, color: T.gray400,
        }}>
          加载中...
        </div>
      )}

      {/* 分类列表 */}
      {!loading && filteredCategories.map(cat => (
        <CategorySection
          key={cat.fanqie_id}
          category={cat}
          books={booksMap[cat.fanqie_id] || []}
        />
      ))}

      {/* 空状态 */}
      {!loading && filteredCategories.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          fontSize: 14, color: T.gray400,
        }}>
          暂无数据，点击右上角「立即同步」抓取
        </div>
      )}
    </div>
  );
}
