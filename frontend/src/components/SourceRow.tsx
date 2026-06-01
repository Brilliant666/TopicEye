'use client';

import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button, cx } from '@/components/ui';
import { timeAgo } from '@/lib/utils';

export interface BackendSource {
  id: number;
  name: string;
  source_type: string;
  url: string;
  keyword?: string | null;
  platform?: string;
  category: string;
  weight: number;
  sort_order?: number;
  fetch_interval_minutes: number;
  status: string;
  last_sync_at: string | null;
  sync_error: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

const typeColors: Record<string, string> = {
  RSS: 'bg-purple-light text-purple',
  RSSHub: 'bg-teal-light text-teal',
  API: 'bg-primary-light text-primary',
  公众号: 'bg-red-light text-red',
  网站: 'bg-amber-light text-amber',
};

const INTERVAL_OPTIONS = [
  { value: 30, label: '30分钟' },
  { value: 60, label: '1小时' },
  { value: 120, label: '2小时' },
  { value: 360, label: '6小时' },
  { value: 720, label: '12小时' },
  { value: 1440, label: '1天' },
];

function formatInterval(minutes: number): string {
  const opt = INTERVAL_OPTIONS.find((o) => o.value === minutes);
  return opt ? opt.label : `${minutes}分钟`;
}

function Spinner() {
  return <div className="h-[18px] w-[18px] animate-spin rounded-full border-2 border-gray-200 border-t-primary" />;
}

interface SourceRowProps {
  source: BackendSource;
  syncing: boolean;
  syncResult: string | null;
  deleting: boolean;
  onSync: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onWeightChange?: (w: number) => void;
  onIntervalChange?: (minutes: number) => void;
}

export default function SourceRowComponent({
  source,
  syncing,
  syncResult,
  deleting,
  onSync,
  onEdit,
  onDelete,
  onWeightChange,
  onIntervalChange,
}: SourceRowProps) {
  const [intervalOpen, setIntervalOpen] = useState(false);
  const typeClass = typeColors[source.source_type] || 'bg-gray-100 text-gray-600';
  const isActive = source.status === 'active' && source.enabled;

  return (
    <div
      onMouseLeave={() => setIntervalOpen(false)}
      className={cx(
        'grid grid-cols-[2fr_1fr_1fr_1.2fr_1fr_1fr_0.8fr_1.5fr] items-center border-b border-gray-100 bg-white px-6 py-3.5 text-[13px] text-gray-700 transition hover:bg-gray-50',
        deleting && 'opacity-50',
      )}
    >
      <div className="min-w-0">
        <span className="font-bold">{source.name}</span>
        {source.url && <div className="mt-0.5 max-w-[220px] truncate text-[11px] text-gray-400">{source.url}</div>}
      </div>

      <span className={cx('w-fit rounded px-2 py-0.5 text-[11px] font-bold', typeClass)}>{source.source_type}</span>
      <span className="text-gray-500">{source.category}</span>

      <div className="min-w-0">
        <span className={cx('text-xs', source.sync_error ? 'text-red' : 'text-gray-400')}>
          {source.sync_error ? '同步失败' : timeAgo(source.last_sync_at)}
        </span>
        {source.sync_error && <div className="mt-0.5 truncate text-[11px] text-red">{source.sync_error}</div>}
        {syncResult && <div className="mt-0.5 truncate text-[11px] text-teal">{syncResult}</div>}
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setIntervalOpen((v) => !v)}
          className={cx(
            'whitespace-nowrap rounded border px-2 py-1 text-[11px] transition',
            intervalOpen ? 'border-primary-border bg-primary-light text-primary' : 'border-gray-200 bg-gray-100 text-gray-600',
          )}
          title="点击修改采集频率"
        >
          {formatInterval(source.fetch_interval_minutes)}
          <ChevronDown size={12} strokeWidth={2} className="ml-1 inline opacity-70" />
        </button>
        {intervalOpen && (
          <div className="absolute left-0 top-[calc(100%+4px)] z-50 min-w-[90px] rounded-xs border border-gray-200 bg-white p-1 shadow-[0_4px_12px_rgba(0,0,0,0.08)]">
            {INTERVAL_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onIntervalChange?.(opt.value);
                  setIntervalOpen(false);
                }}
                className={cx(
                  'block w-full rounded px-2.5 py-1.5 text-left text-xs transition hover:bg-gray-50',
                  opt.value === source.fetch_interval_minutes ? 'bg-primary-light font-bold text-primary' : 'text-gray-700',
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex cursor-pointer items-center gap-0.5" title={`权重 ${source.weight}/5 — 影响精选加分：${source.weight > 3 ? '+' : ''}${(source.weight - 3) * 8} 分`}>
        {[1, 2, 3, 4, 5].map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => onWeightChange?.(w)}
            className={cx('text-[11px] transition', w <= source.weight ? 'text-primary' : 'text-gray-200')}
          >
            ●
          </button>
        ))}
        <span className="ml-1 text-[10px] text-gray-400">{(source.weight - 3) * 8 > 0 ? '+' : ''}{(source.weight - 3) * 8}</span>
      </div>

      <div className="flex items-center gap-1.5">
        <span className={cx('h-2 w-2 rounded-full', isActive ? 'bg-teal' : 'bg-red')} />
        <span className={cx('text-[11px]', isActive ? 'text-teal' : 'text-red')}>
          {source.enabled ? (source.status === 'active' ? '正常' : source.status) : '已禁用'}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Button type="button" onClick={onSync} disabled={syncing} variant={syncing ? 'secondary' : 'success'} className="min-h-7 px-2.5 py-1 text-[11px]">
          {syncing ? <Spinner /> : null}
          {syncing ? '同步中' : '同步'}
        </Button>
        <Button type="button" onClick={onEdit} variant="secondary" className="min-h-7 bg-purple-light px-2.5 py-1 text-[11px] text-purple hover:text-purple">
          编辑
        </Button>
        <Button type="button" onClick={onDelete} disabled={deleting} variant="ghost" className="min-h-7 px-2.5 py-1 text-[11px] text-red hover:text-red">
          {deleting ? '删除中…' : '删除'}
        </Button>
      </div>
    </div>
  );
}

export { Spinner };
