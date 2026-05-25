'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';
import { fanqieApi, qimaoApi, type FanqieCategory, type FanqieBook, type QimaoBook } from '@/lib/api';

/* ── Constants ── */

const GROUP_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  male: { label: '男频', color: '#2563EB', bg: '#EFF6FF' },
  female: { label: '女频', color: '#E11D48', bg: '#FFF1F2' },
};

const RANK_TYPE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  new: { label: '新书榜', color: '#7C3AED', bg: '#F5F3FF' },
  reading: { label: '阅读榜', color: '#059669', bg: '#ECFDF5' },
};

const QIMAO_RANK_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  hot: { label: '大热', color: '#DC2626', bg: '#FEF2F2' },
  new: { label: '新书', color: '#7C3AED', bg: '#F5F3FF' },
  over: { label: '完结', color: '#D97706', bg: '#FFFBEB' },
  collect: { label: '收藏', color: '#2563EB', bg: '#EFF6FF' },
  update: { label: '更新', color: '#059669', bg: '#ECFDF5' },
};

const QIMAO_CHANNEL_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  boy: { label: '男频', color: '#2563EB', bg: '#EFF6FF' },
  girl: { label: '女频', color: '#E11D48', bg: '#FFF1F2' },
};

/* ── Formatters ── */

function formatCount(v: string | number | undefined): string {
  if (!v) return '-';
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (n >= 100000000) return (n / 100000000).toFixed(1) + '亿';
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return String(n);
}

/* ── Book Card Components ── */

function FanqieCard({ book, rankTab }: { book: FanqieBook; rankTab: string }) {
  const groupKey = book.rank_type === 'new' ? 'male' : 'female';
  const group = GROUP_LABELS[groupKey] ?? GROUP_LABELS.male;
  const rankInfo = RANK_TYPE_LABELS[rankTab];
  const pos = book.position;

  return (
    <div style={{
      display: 'flex', gap: 12, padding: '14px 16px', borderBottom: `1px solid ${T.gray100}`,
      alignItems: 'flex-start',
    }}>
      <div style={{
        fontSize: 18, fontWeight: 700, color: pos <= 3 ? '#F59E0B' : T.gray300,
        minWidth: 28, textAlign: 'center', lineHeight: '80px',
      }}>
        {pos}
      </div>
      <img
        src={book.thumb_uri || '/placeholder.png'}
        alt={book.book_name}
        style={{ width: 60, height: 80, objectFit: 'cover', borderRadius: 6, flexShrink: 0, background: T.gray100 }}
        onError={(e) => { (e.target as HTMLImageElement).src = `https://via.placeholder.com/60x80?text=${encodeURIComponent(book.book_name?.slice(0, 2) ?? '书')}`; }}
      />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <div style={{ fontWeight: 700, fontSize: 15, color: T.gray900, marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {book.book_name}
        </div>
        <div style={{ fontSize: 12, color: T.gray500, marginBottom: 6 }}>{book.author}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {rankInfo && (
            <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 4, background: rankInfo.bg, color: rankInfo.color }}>
              {rankInfo.label}
            </span>
          )}
          {typeof book.rank_pos_diff === 'number' && book.rank_pos_diff !== 0 && (
            <span style={{
              fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
              background: book.rank_pos_diff > 0 ? '#ECFDF5' : '#FEF2F2',
              color: book.rank_pos_diff > 0 ? '#059669' : '#DC2626',
            }}>
              {book.rank_pos_diff > 0 ? `↑${book.rank_pos_diff}` : `↓${Math.abs(book.rank_pos_diff)}`}
            </span>
          )}
          {book.read_count && (
            <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
              {formatCount(book.read_count)}阅读
            </span>
          )}
          {book.word_number && (
            <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
              {formatCount(book.word_number)}字
            </span>
          )}
        </div>
        {book.abstract && (
          <div style={{ fontSize: 11, color: T.gray400, marginTop: 5, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {book.abstract}
          </div>
        )}
      </div>
    </div>
  );
}

function QimaoCard({ book }: { book: QimaoBook }) {
  const pos = book.position;
  const changeColor = book.index_change > 0 ? '#059669' : book.index_change < 0 ? '#DC2626' : T.gray400;

  return (
    <div style={{
      display: 'flex', gap: 12, padding: '14px 16px', borderBottom: `1px solid ${T.gray100}`,
      alignItems: 'flex-start',
    }}>
      <div style={{
        fontSize: 18, fontWeight: 700, color: pos <= 3 ? '#F59E0B' : T.gray300,
        minWidth: 28, textAlign: 'center', lineHeight: '80px',
      }}>
        {pos}
      </div>
      <img
        src={book.thumb_uri || '/placeholder.png'}
        alt={book.title}
        style={{ width: 60, height: 80, objectFit: 'cover', borderRadius: 6, flexShrink: 0, background: T.gray100 }}
        onError={(e) => { (e.target as HTMLImageElement).src = `https://via.placeholder.com/60x80?text=${encodeURIComponent(book.title?.slice(0, 2) ?? '书')}`; }}
      />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: T.gray900, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
            {book.title}
          </div>
          {book.is_continue_top === 1 && (
            <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 4, background: '#FEF3C7', color: '#D97706', flexShrink: 0 }}>
              霸榜
            </span>
          )}
          {book.is_over === 1 && (
            <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 4, background: '#F3F4F6', color: '#6B7280', flexShrink: 0 }}>
              完结
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: T.gray500, marginBottom: 6 }}>
          {book.author}
          {book.category1_name && book.category2_name && (
            <span style={{ marginLeft: 8, color: T.gray400 }}>
              {book.category1_name} · {book.category2_name}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {book.collect_count != null && (
            <span style={{ fontSize: 10, color: '#DC2626', fontFamily: T.mono, fontWeight: 600 }}>
              ♥ {formatCount(book.collect_count)}
            </span>
          )}
          {book.words_num && (
            <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
              {book.words_num}
            </span>
          )}
          {book.index_change !== 0 && (
            <span style={{ fontSize: 10, fontWeight: 600, fontFamily: T.mono, color: changeColor }}>
              {book.index_change > 0 ? `↑${book.index_change}` : book.index_change < 0 ? `↓${Math.abs(book.index_change)}` : '='}
            </span>
          )}
        </div>
        {book.abstract && (
          <div style={{ fontSize: 11, color: T.gray400, marginTop: 5, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {book.abstract.replace(/\n/g, ' ')}
          </div>
        )}
        {book.latest_chapter_title && (
          <div style={{ fontSize: 10, color: T.gray400, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            更新 {book.latest_chapter_title}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main Page ── */

export default function FanqiePage() {
  const [platform, setPlatform] = useState<'fanqie' | 'qimao'>('fanqie');

  /* ── 番茄状态 ── */
  const [categories, setCategories] = useState<FanqieCategory[]>([]);
  const [booksMap, setBooksMap] = useState<Record<string, FanqieBook[]>>({});
  const [initLoading, setInitLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [rankTab, setRankTab] = useState<'new' | 'reading'>('reading');
  const [activeCat, setActiveCat] = useState<string>('');
  const [groupTab, setGroupTab] = useState<'male' | 'female'>('male');

  /* ── 七猫状态 ── */
  const [qimaoBooks, setQimaoBooks] = useState<QimaoBook[]>([]);
  const [qimaoLoading, setQimaoLoading] = useState(false);
  const [qimaoSyncing, setQimaoSyncing] = useState(false);
  const [qimaoChannel, setQimaoChannel] = useState<'boy' | 'girl'>('boy');
  const [qimaoRank, setQimaoRank] = useState<keyof typeof QIMAO_RANK_LABELS>('hot');

  /* ── 番茄数据拉取 ── */
  const fetchFanqieData = useCallback(async (rt: string, isInit = false) => {
    if (isInit) setInitLoading(true); else setSwitching(true);
    try {
      const cats = categories.length ? categories : await fanqieApi.categories();
      if (isInit) setCategories(cats);

      const catId = activeCat || (cats[0]?.fanqie_id ?? '');
      if (isInit && catId) setActiveCat(catId);

      const result = await fanqieApi.categoryBooks(catId, { rank_type: rt });
      const key = `${catId}|${rt}`;
      setBooksMap(prev => ({ ...prev, [key]: result.books }));
    } catch (e) {
      console.error('fetch error', e);
    } finally {
      setInitLoading(false);
      setSwitching(false);
    }
  }, [categories, activeCat]);

  // groupTab 切换 → 重置分类
  useEffect(() => {
    if (platform !== 'fanqie' || categories.length === 0) return;
    const first = categories.find(c => c.group === groupTab);
    if (first && first.fanqie_id !== activeCat) {
      setActiveCat(first.fanqie_id);
      setBooksMap({});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupTab, categories]);

  useEffect(() => {
    if (platform !== 'fanqie') return;
    void fetchFanqieData(rankTab, true);
  }, []); // eslint-disable-line

  useEffect(() => {
    if (platform !== 'fanqie') return;
    void fetchFanqieData(rankTab);
  }, [rankTab, activeCat]); // eslint-disable-line

  /* ── 七猫数据拉取 ── */
  const fetchQimaoData = useCallback(async () => {
    setQimaoLoading(true);
    try {
      const result = await qimaoApi.list(qimaoChannel, qimaoRank);
      setQimaoBooks(result.books);
    } catch (e) {
      console.error('qimao fetch error', e);
    } finally {
      setQimaoLoading(false);
    }
  }, [qimaoChannel, qimaoRank]);

  useEffect(() => {
    if (platform !== 'qimao') return;
    void fetchQimaoData();
  }, [platform, qimaoChannel, qimaoRank]); // eslint-disable-line

  /* ── 统计卡片 ── */
  const fanqieBooks = (() => {
    const key = `${activeCat}|${rankTab}`;
    return booksMap[key] ?? [];
  })();

  const currentBooks = platform === 'fanqie' ? fanqieBooks : qimaoBooks;

  const statCards = [
    { label: platform === 'fanqie' ? '番茄小说' : '七猫小说', value: currentBooks.length },
    { label: '平台', value: platform === 'fanqie' ? '番茄' : '七猫' },
  ];

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* 顶栏 */}
      <div style={{
        height: 52, background: '#fff', borderBottom: `1px solid ${T.gray100}`,
        display: 'flex', alignItems: 'center', padding: '0 20px', gap: 12, flexShrink: 0,
      }}>
        <span style={{ fontWeight: 800, fontSize: 16, color: T.gray900, marginRight: 8 }}>网文雷达</span>
        <div style={{ height: 20, width: 1, background: T.gray200 }} />
        {/* 平台切换 */}
        <div style={{ display: 'flex', gap: 4 }}>
          {(['fanqie', 'qimao'] as const).map(p => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              style={{
                padding: '4px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                fontSize: 13, fontWeight: 600,
                background: platform === p ? T.gray900 : '#fff',
                color: platform === p ? '#fff' : T.gray600,
                boxShadow: platform === p ? '0 1px 4px rgba(0,0,0,0.15)' : `0 0 0 1px ${T.gray200}`,
                transition: 'all 0.15s',
              }}
            >
              {p === 'fanqie' ? '番茄小说' : '七猫小说'}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        {platform === 'fanqie' ? (
          <button
            onClick={async () => {
              setSyncing(true);
              try { await fanqieApi.sync(); await fetchFanqieData(rankTab, true); }
              catch (e) { console.error(e); }
              finally { setSyncing(false); }
            }}
            disabled={syncing}
            style={{
              padding: '5px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: 600, background: syncing ? T.gray200 : '#2563EB',
              color: '#fff', transition: 'background 0.2s',
            }}
          >
            {syncing ? '同步中…' : '🔄 同步番茄'}
          </button>
        ) : (
          <button
            onClick={async () => {
              setQimaoSyncing(true);
              try { await qimaoApi.sync(); await fetchQimaoData(); }
              catch (e) { console.error(e); }
              finally { setQimaoSyncing(false); }
            }}
            disabled={qimaoSyncing}
            style={{
              padding: '5px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: 600, background: qimaoSyncing ? T.gray200 : '#DC2626',
              color: '#fff', transition: 'background 0.2s',
            }}
          >
            {qimaoSyncing ? '同步中…' : '🔄 同步七猫'}
          </button>
        )}
      </div>

      {/* 统计卡片 */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, padding: '12px 16px',
        background: '#fff', borderBottom: `1px solid ${T.gray100}`, flexShrink: 0,
      }}>
        {statCards.map(({ label, value }) => (
          <div key={label} style={{
            background: '#F9FAFB', borderRadius: 10, padding: '10px 14px',
            border: `1px solid ${T.gray100}`,
          }}>
            <div style={{ fontSize: 11, color: T.gray500, marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: T.gray900 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* 番茄：榜单 Tab */}
      {platform === 'fanqie' && (
        <div style={{
          display: 'flex', gap: 6, padding: '10px 16px', background: '#fff',
          borderBottom: `1px solid ${T.gray100}`, flexShrink: 0, overflowX: 'auto',
        }}>
          {/* 男频/女频 */}
          {(Object.entries(GROUP_LABELS) as [string, typeof GROUP_LABELS[string]][]).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setGroupTab(k as 'male' | 'female')}
              style={{
                padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                background: groupTab === k ? v.color : '#fff',
                color: groupTab === k ? '#fff' : T.gray600,
                boxShadow: groupTab === k ? `0 2px 8px ${v.color}44` : `0 0 0 1px ${T.gray200}`,
              }}
            >
              {v.label}
            </button>
          ))}
          <div style={{ width: 1, height: 20, background: T.gray200, margin: '0 4px' }} />
          {/* 新书/阅读 */}
          {(Object.entries(RANK_TYPE_LABELS) as [string, typeof RANK_TYPE_LABELS[string]][]).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setRankTab(k as 'new' | 'reading')}
              style={{
                padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                background: rankTab === k ? v.color : '#fff',
                color: rankTab === k ? '#fff' : T.gray600,
                boxShadow: rankTab === k ? `0 2px 8px ${v.color}44` : `0 0 0 1px ${T.gray200}`,
              }}
            >
              {v.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          {/* 分类横滚（仅当前性别） */}
          <div style={{ display: 'flex', gap: 4, overflowX: 'auto', flex: 1 }}>
            {categories.filter(c => c.group === groupTab).slice(0, 12).map(cat => (
              <button
                key={cat.fanqie_id}
                onClick={() => setActiveCat(cat.fanqie_id)}
                style={{
                  padding: '4px 10px', borderRadius: 16, border: 'none', cursor: 'pointer',
                  fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
                  background: activeCat === cat.fanqie_id ? T.gray900 : '#F3F4F6',
                  color: activeCat === cat.fanqie_id ? '#fff' : T.gray500,
                }}
              >
                {cat.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 七猫：频道+榜单 Tab */}
      {platform === 'qimao' && (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 16px',
          background: '#fff', borderBottom: `1px solid ${T.gray100}`, flexShrink: 0,
        }}>
          {/* 频道 */}
          <div style={{ display: 'flex', gap: 6 }}>
            {(Object.entries(QIMAO_CHANNEL_LABELS) as [string, typeof QIMAO_CHANNEL_LABELS[string]][]).map(([k, v]) => (
              <button
                key={k}
                onClick={() => setQimaoChannel(k as 'boy' | 'girl')}
                style={{
                  padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                  fontSize: 13, fontWeight: 600,
                  background: qimaoChannel === k ? v.color : '#fff',
                  color: qimaoChannel === k ? '#fff' : T.gray600,
                  boxShadow: qimaoChannel === k ? `0 2px 8px ${v.color}44` : `0 0 0 1px ${T.gray200}`,
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
          {/* 榜单类型 */}
          <div style={{ display: 'flex', gap: 4, overflowX: 'auto' }}>
            {(Object.entries(QIMAO_RANK_LABELS) as [string, typeof QIMAO_RANK_LABELS[string]][]).map(([k, v]) => (
              <button
                key={k}
                onClick={() => setQimaoRank(k as keyof typeof QIMAO_RANK_LABELS)}
                style={{
                  padding: '4px 12px', borderRadius: 16, border: 'none', cursor: 'pointer',
                  fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
                  background: qimaoRank === k ? v.color : '#F3F4F6',
                  color: qimaoRank === k ? '#fff' : T.gray500,
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 内容区 */}
      <div style={{ flex: 1, overflowY: 'auto', position: 'relative', background: '#fff' }}>
        {platform === 'fanqie' ? (
          initLoading ? (
            <div style={{ textAlign: 'center', padding: '60px 0', fontSize: 14, color: T.gray400 }}>
              加载中...
            </div>
          ) : switching ? (
            <div style={{ textAlign: 'center', padding: '60px 0', fontSize: 14, color: T.gray400 }}>
              切换中…
            </div>
          ) : currentBooks.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 0', fontSize: 14, color: T.gray400 }}>
              暂无数据
            </div>
          ) : (
            (currentBooks as FanqieBook[]).map(book => <FanqieCard key={book.book_id} book={book} rankTab={rankTab} />)
          )
        ) : (
          qimaoLoading ? (
            <div style={{ textAlign: 'center', padding: '60px 0', fontSize: 14, color: T.gray400 }}>
              加载中…
            </div>
          ) : qimaoBooks.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px 0', fontSize: 14, color: T.gray400 }}>
              暂无数据
            </div>
          ) : (
            qimaoBooks.map(book => <QimaoCard key={`${book.book_id}-${book.rank_type}`} book={book} />)
          )
        )}
      </div>
    </div>
  );
}
