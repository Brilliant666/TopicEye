'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { T, CATEGORIES, SOURCE_TYPE_COLOR_MAP } from '@/lib/design-tokens';
import { contentsApi } from '@/lib/api';
import type { ContentItem } from '@/types';

// ─── Helpers ──

function parseUTC(s: string): Date {
  const normalized = s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s) ? s : s + 'Z';
  return new Date(normalized);
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '-';
  const date = parseUTC(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  return `${months} 个月前`;
}

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  pending:  { bg: T.gray100, color: T.gray500 },
  analyzed: { bg: T.tealLight, color: T.teal },
  error:    { bg: T.redLight, color: T.red },
};

const PAGE_SIZE = 50;

// ─── Spinner ───

function Spinner() {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 18,
        height: 18,
        border: `2px solid ${T.gray200}`,
        borderTopColor: T.primary,
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}
    />
  );
}

// ─── Page Component ───

export default function ContentsPage() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<string>('全部');

  // ─── Fetch contents ───
  const fetchContents = useCallback(async (p: number, cat: string) => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, unknown> = { page: p, page_size: PAGE_SIZE };
      if (cat && cat !== '全部') params.category = cat;
      const res = await contentsApi.list(params);
      const list = res?.items || [];
      setItems(list as ContentItem[]);
      setTotal(res?.total ?? list.length);
      setPage(res?.page ?? p);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '加载内容列表失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchContents(1, category);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleCategoryChange = (cat: string) => {
    setCategory(cat);
    setPage(1);
  };

  const handlePrev = () => {
    if (page > 1) {
      const next = page - 1;
      setPage(next);
      fetchContents(next, category);
    }
  };

  const handleNext = () => {
    if (page < totalPages) {
      const next = page + 1;
      setPage(next);
      fetchContents(next, category);
    }
  };

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900, marginBottom: 6 }}>
          内容列表
        </h1>
        <p style={{ fontSize: 13, color: T.gray400 }}>
          从各信源采集到的原始内容 · 共{' '}
          <b style={{ fontFamily: T.mono, color: T.gray600 }}>{total}</b> 条
        </p>
      </div>

      {/* Category Filter Bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {CATEGORIES.map((cat) => {
          const active = category === cat;
          return (
            <button
              key={cat}
              onClick={() => handleCategoryChange(cat)}
              style={{
                padding: '6px 14px',
                fontSize: 12,
                fontWeight: active ? 600 : 500,
                background: active ? T.primaryLight : T.white,
                color: active ? T.primary : T.gray600,
                border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                borderRadius: T.radiusXs,
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {cat}
            </button>
          );
        })}
      </div>

      {/* Error Banner */}
      {error && (
        <div
          style={{
            padding: '10px 16px',
            marginBottom: 16,
            background: T.redLight,
            color: T.red,
            borderRadius: T.radiusSm,
            fontSize: 13,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{
              background: 'none',
              border: 'none',
              color: T.red,
              cursor: 'pointer',
              fontSize: 16,
              fontWeight: 700,
              lineHeight: 1,
              padding: '0 4px',
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: 200,
            color: T.gray400,
            fontSize: 14,
            gap: 10,
          }}
        >
          <Spinner />
          <span>加载中…</span>
        </div>
      )}

      {/* Table */}
      {!loading && (
        <div
          style={{
            background: T.white,
            borderRadius: T.radius,
            border: `1px solid ${T.gray100}`,
            overflow: 'hidden',
          }}
        >
          {/* Table Header */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '3fr 1.2fr 0.8fr 1.5fr 1fr 0.8fr',
              padding: '12px 24px',
              background: T.gray50,
              borderBottom: `1px solid ${T.gray200}`,
              fontSize: 12,
              fontWeight: 600,
              color: T.gray500,
              textTransform: 'uppercase' as const,
              letterSpacing: '0.05em',
            }}
          >
            <span>标题</span>
            <span>来源</span>
            <span>分类</span>
            <span>标签</span>
            <span>发布时间</span>
            <span>状态</span>
          </div>

          {/* Empty State */}
          {items.length === 0 && (
            <div
              style={{
                padding: '48px 24px',
                textAlign: 'center' as const,
                color: T.gray400,
                fontSize: 14,
              }}
            >
              暂无内容数据
            </div>
          )}

          {/* Rows */}
          {items.map((item) => (
            <ContentRow key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {!loading && total > 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 16,
            fontSize: 13,
            color: T.gray500,
          }}
        >
          <span>
            第 <b style={{ fontFamily: T.mono }}>{page}</b> / <b style={{ fontFamily: T.mono }}>{totalPages}</b> 页，共 {total} 条
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handlePrev}
              disabled={page <= 1}
              style={{
                padding: '6px 16px',
                fontSize: 13,
                fontWeight: 500,
                background: page <= 1 ? T.gray100 : T.white,
                color: page <= 1 ? T.gray300 : T.gray600,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radiusXs,
                cursor: page <= 1 ? 'not-allowed' : 'pointer',
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <ChevronLeft size={14} strokeWidth={2} />
                上一页
              </span>
            </button>
            <button
              onClick={handleNext}
              disabled={page >= totalPages}
              style={{
                padding: '6px 16px',
                fontSize: 13,
                fontWeight: 500,
                background: page >= totalPages ? T.gray100 : T.white,
                color: page >= totalPages ? T.gray300 : T.gray600,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radiusXs,
                cursor: page >= totalPages ? 'not-allowed' : 'pointer',
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                下一页
                <ChevronRight size={14} strokeWidth={2} />
              </span>
            </button>
          </div>
        </div>
      )}

      {/* Spinner keyframe */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

// ─── Content Row ───

function ContentRow({ item }: { item: ContentItem }) {
  const statusKey = item.status || 'pending';
  const statusStyle = STATUS_STYLE[statusKey] || STATUS_STYLE.pending;
  const sourceTypeColor = SOURCE_TYPE_COLOR_MAP[item.source_type] || { bg: T.gray100, color: T.gray500 };
  const statusLabel: Record<string, string> = {
    pending: '待处理',
    analyzed: '已分析',
    error: '错误',
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '3fr 1.2fr 0.8fr 1.5fr 1fr 0.8fr',
        padding: '14px 24px',
        borderBottom: `1px solid ${T.gray100}`,
        alignItems: 'center',
        fontSize: 13,
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = T.gray50)}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      {/* 标题 */}
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: 12 }}>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: T.gray800,
              textDecoration: 'none',
              fontWeight: 500,
            }}
            onMouseEnter={(e) => {
              (e.target as HTMLElement).style.color = T.primary;
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLElement).style.color = T.gray800;
            }}
          >
            {item.title || '无标题'}
          </a>
        ) : (
          <span style={{ color: T.gray800, fontWeight: 500 }}>{item.title || '无标题'}</span>
        )}
      </div>

      {/* 来源 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, overflow: 'hidden' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T.gray700 }}>
          {item.source_name}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 6px',
            borderRadius: 4,
            background: sourceTypeColor.bg,
            color: sourceTypeColor.color,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {item.source_type}
        </span>
      </div>

      {/* 分类 */}
      <div>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            padding: '3px 8px',
            borderRadius: 4,
            background: T.primaryLight,
            color: T.primary,
            whiteSpace: 'nowrap',
          }}
        >
          {item.category}
        </span>
      </div>

      {/* 标签 */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', overflow: 'hidden' }}>
        {item.tags && item.tags.length > 0
          ? item.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 10,
                  fontWeight: 500,
                  padding: '2px 7px',
                  borderRadius: 4,
                  background: T.purpleLight,
                  color: T.purple,
                  whiteSpace: 'nowrap',
                }}
              >
                {tag}
              </span>
            ))
          : <span style={{ color: T.gray300 }}>-</span>
        }
        {item.tags && item.tags.length > 3 && (
          <span style={{ fontSize: 10, color: T.gray400 }}>+{item.tags.length - 3}</span>
        )}
      </div>

      {/* 发布时间 */}
      <div style={{ color: T.gray500, fontFamily: T.mono, fontSize: 12 }}>
        {timeAgo(item.published_at)}
      </div>

      {/* 状态 */}
      <div>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            padding: '3px 10px',
            borderRadius: 4,
            background: statusStyle.bg,
            color: statusStyle.color,
          }}
        >
          {statusLabel[statusKey] || statusKey}
        </span>
      </div>
    </div>
  );
}
