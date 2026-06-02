'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Archive, ExternalLink, FileText, Filter, RefreshCw, Search, Star, Trash2 } from 'lucide-react';
import { favoritesApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';
import { Badge, Button, Panel, cx } from '@/components/ui';
import type { FavoriteItem, FavoriteStatus, FavoriteTargetType } from '@/types';

const TYPE_OPTIONS: Array<{ value: FavoriteTargetType | ''; label: string }> = [
  { value: '', label: '全部' },
  { value: 'content', label: '内容' },
  { value: 'book', label: '小说' },
  { value: 'source', label: '信源' },
  { value: 'trend', label: '趋势' },
  { value: 'author', label: '作者' },
  { value: 'topic_group', label: '话题组' },
];

const STATUS_OPTIONS: Array<{ value: FavoriteStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'inbox', label: '待处理' },
  { value: 'researching', label: '研究中' },
  { value: 'drafting', label: '创作中' },
  { value: 'archived', label: '已归档' },
];

const STATUS_LABEL: Record<FavoriteStatus, string> = {
  inbox: '待处理',
  researching: '研究中',
  drafting: '创作中',
  archived: '已归档',
};

const TYPE_LABEL: Record<FavoriteTargetType, string> = {
  content: '内容',
  book: '小说',
  source: '信源',
  trend: '趋势',
  author: '作者',
  topic_group: '话题组',
};

function parseUTC(s: string): Date {
  const normalized = s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s) ? s : s + 'Z';
  return new Date(normalized);
}

function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const date = parseUTC(dateStr);
  const hours = Math.floor((Date.now() - date.getTime()) / 3600000);
  if (hours < 1) return '刚刚';
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return `${Math.floor(days / 30)} 个月前`;
}

function getSnapshotText(item: FavoriteItem): string {
  const snapshot = item.snapshot || {};
  const summary = snapshot.summary;
  if (typeof summary === 'string' && summary.trim()) return summary.replace(/<[^>]+>/g, '').slice(0, 180);
  const category = snapshot.category;
  const platform = snapshot.platform;
  return [typeof category === 'string' ? category : null, typeof platform === 'string' ? platform : null].filter(Boolean).join(' · ');
}

export default function FavoritesPage() {
  const { refreshCounts } = useAppContext();
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetType, setTargetType] = useState<FavoriteTargetType | ''>('');
  const [status, setStatus] = useState<FavoriteStatus | ''>('');
  const [keyword, setKeyword] = useState('');
  const [draftKeyword, setDraftKeyword] = useState('');
  const [pendingId, setPendingId] = useState<number | null>(null);

  const fetchFavorites = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await favoritesApi.list({
        page_size: 100,
        target_type: targetType,
        status,
        keyword: keyword.trim() || undefined,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : '收藏夹加载失败');
    } finally {
      setLoading(false);
    }
  }, [targetType, status, keyword]);

  useEffect(() => {
    void fetchFavorites();
  }, [fetchFavorites]);

  const counts = useMemo(() => {
    const content = items.filter((item) => item.target_type === 'content').length;
    const active = items.filter((item) => item.status !== 'archived').length;
    return { content, active };
  }, [items]);

  const handleSearch = () => setKeyword(draftKeyword);

  const updateStatus = async (item: FavoriteItem, nextStatus: FavoriteStatus) => {
    setPendingId(item.id);
    setError(null);
    try {
      const updated = await favoritesApi.update(item.id, { status: nextStatus });
      setItems((prev) => prev.map((row) => (row.id === item.id ? updated : row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : '状态更新失败');
    } finally {
      setPendingId(null);
    }
  };

  const removeFavorite = async (item: FavoriteItem) => {
    setPendingId(item.id);
    setError(null);
    try {
      await favoritesApi.delete(item.id);
      setItems((prev) => prev.filter((row) => row.id !== item.id));
      setTotal((prev) => Math.max(0, prev - 1));
      refreshCounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除收藏失败');
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="fade-in h-full overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
      <div className="mb-6 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="mb-1.5 text-[26px] font-bold text-gray-900">收藏中心</h1>
          <p className="text-[13px] text-gray-400">
            共 <b className="font-mono text-primary">{total}</b> 条收藏，{counts.active} 条待推进
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <StatPill label="内容" value={counts.content} />
          <StatPill label="工作中" value={counts.active} />
        </div>
      </div>

      <Panel className="mb-5 p-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Filter size={15} className="text-gray-400" />
            {TYPE_OPTIONS.map((option) => (
              <button
                key={option.value || 'all'}
                type="button"
                onClick={() => setTargetType(option.value)}
                className={cx(
                  'rounded-sm border px-3 py-1.5 text-xs font-bold transition',
                  targetType === option.value ? 'border-primary bg-primary-light text-primary' : 'border-gray-200 bg-white text-gray-500 hover:text-gray-900',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as FavoriteStatus | '')}
              className="h-9 rounded-sm border border-gray-200 bg-white px-3 text-xs font-bold text-gray-600 outline-none focus:border-primary-border"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value || 'all'} value={option.value}>{option.label}</option>
              ))}
            </select>
            <div className="flex min-w-0 items-center rounded-sm border border-gray-200 bg-white px-2 focus-within:border-primary-border">
              <Search size={14} className="shrink-0 text-gray-400" />
              <input
                value={draftKeyword}
                onChange={(event) => setDraftKeyword(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') handleSearch(); }}
                className="h-8 min-w-0 bg-transparent px-2 text-xs outline-none"
                placeholder="搜索标题"
              />
              <button type="button" onClick={handleSearch} className="text-xs font-bold text-primary">搜索</button>
            </div>
          </div>
        </div>
      </Panel>

      {error && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-sm border border-red/20 bg-red-light px-4 py-3 text-[13px] text-red">
          <div className="flex min-w-0 items-center gap-2">
            <AlertCircle size={15} className="shrink-0" />
            <span className="break-words">{error}</span>
          </div>
          <Button type="button" variant="danger" onClick={() => void fetchFavorites()}>
            <RefreshCw size={13} />
            重试
          </Button>
        </div>
      )}

      {loading ? (
        <div className="p-20 text-center text-sm text-gray-400">加载中...</div>
      ) : items.length === 0 ? (
        <div className="p-20 text-center text-sm text-gray-400">
          <Star size={38} className="mx-auto mb-4 text-gray-300 opacity-70" strokeWidth={1.8} />
          <div>当前筛选下没有收藏</div>
          <div className="mt-1 text-xs">从内容、榜单、信源或趋势入口加入收藏后会出现在这里</div>
        </div>
      ) : (
        <div className="grid gap-3 pb-10">
          {items.map((item) => (
            <FavoriteRow
              key={item.id}
              item={item}
              pending={pendingId === item.id}
              onStatus={updateStatus}
              onRemove={removeFavorite}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-sm border border-gray-200 bg-white px-4 py-2">
      <div className="text-[11px] font-bold text-gray-400">{label}</div>
      <div className="font-mono text-lg font-black text-gray-900">{value}</div>
    </div>
  );
}

function FavoriteRow({
  item,
  pending,
  onStatus,
  onRemove,
}: {
  item: FavoriteItem;
  pending: boolean;
  onStatus: (item: FavoriteItem, status: FavoriteStatus) => void;
  onRemove: (item: FavoriteItem) => void;
}) {
  const snapshotText = getSnapshotText(item);
  const statusTone = item.status === 'inbox' ? 'amber' : item.status === 'researching' ? 'teal' : item.status === 'drafting' ? 'primary' : 'neutral';
  return (
    <Panel className="px-5 py-4 transition hover:shadow-md">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone={item.target_type === 'content' ? 'primary' : item.target_type === 'book' ? 'purple' : 'neutral'} className="rounded px-2 py-0.5">
              {TYPE_LABEL[item.target_type]}
            </Badge>
            <Badge tone={statusTone} className="rounded px-2 py-0.5">{STATUS_LABEL[item.status]}</Badge>
            {item.source_name && <span className="text-[11px] font-bold text-gray-400">{item.source_name}</span>}
            <span className="text-[11px] text-gray-300">·</span>
            <span className="text-[11px] font-bold text-gray-400">{timeAgo(item.created_at)}</span>
          </div>
          <h3 className="mb-1 text-[15px] font-semibold leading-6 text-gray-900">{item.title}</h3>
          {snapshotText && <p className="line-clamp-2 text-[13px] leading-6 text-gray-500">{snapshotText}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <select
            value={item.status}
            disabled={pending}
            onChange={(event) => onStatus(item, event.target.value as FavoriteStatus)}
            className="h-8 rounded-sm border border-gray-200 bg-white px-2 text-xs font-bold text-gray-600 outline-none disabled:cursor-wait disabled:opacity-60"
          >
            {STATUS_OPTIONS.filter((option) => option.value).map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1 rounded-sm border border-gray-200 bg-white px-2 text-xs font-bold text-gray-500 hover:text-primary"
            >
              <ExternalLink size={13} />
              原文
            </a>
          )}
          {item.target_type === 'content' && item.target_id && (
            <a
              href={`/topics/${item.target_id}`}
              className="inline-flex h-8 items-center gap-1 rounded-sm border border-gray-200 bg-white px-2 text-xs font-bold text-gray-500 hover:text-primary"
            >
              <FileText size={13} />
              详情
            </a>
          )}
          <button
            type="button"
            disabled={pending}
            onClick={() => onRemove(item)}
            className="inline-flex h-8 items-center gap-1 rounded-sm border border-red-light bg-red-light px-2 text-xs font-bold text-red disabled:cursor-wait disabled:opacity-60"
            title="删除收藏"
          >
            {item.status === 'archived' ? <Archive size={13} /> : <Trash2 size={13} />}
            删除
          </button>
        </div>
      </div>
    </Panel>
  );
}
