'use client';

import React, { useState } from 'react';
import { T } from '@/lib/design-tokens';
import { timeAgo } from '@/lib/utils';

// ─── Backend Source type (local to sources page) ───

export interface BackendSource {
  id: number;
  name: string;
  source_type: string;
  url: string;
  keyword?: string;
  platform?: string;
  category: string;
  weight: number;
  status: string;
  last_sync_at: string | null;
  sync_error: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

const typeColors: Record<string, { bg: string; color: string }> = {
  'RSS': { bg: '#EEF2FF', color: '#4F46E5' },
  'RSSHub': { bg: '#F0FDF4', color: '#16A34A' },
  '公众号': { bg: '#FFF1F2', color: '#E11D48' },
  '网站': { bg: '#FEF3C7', color: '#92400E' },
};

// ─── Spinner ───

function Spinner() {
  return (
    <div
      style={{
        width: 18,
        height: 18,
        border: `2px solid ${T.gray200}`,
        borderTopColor: T.primary,
        borderRadius: '50%',
        animation: 'spin 0.6s linear infinite',
      }}
    />
  );
}

// ─── Source Row ───

interface SourceRowProps {
  source: BackendSource;
  syncing: boolean;
  syncResult: string | null;
  deleting: boolean;
  onSync: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onWeightChange?: (w: number) => void;
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
}: SourceRowProps) {
  const [hovered, setHovered] = useState(false);
  const tc = typeColors[source.source_type] || { bg: T.gray100, color: T.gray600 };
  const isActive = source.status === 'active' && source.enabled;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr 0.8fr 1.5fr',
        padding: '14px 24px',
        borderBottom: `1px solid ${T.gray100}`,
        fontSize: 13,
        color: T.gray700,
        alignItems: 'center',
        transition: 'background 0.1s',
        cursor: 'default',
        background: hovered ? T.gray50 : T.white,
        opacity: deleting ? 0.5 : 1,
      }}
    >
      {/* Name */}
      <div>
        <span style={{ fontWeight: 500 }}>{source.name}</span>
        {source.url && (
          <div style={{ fontSize: 11, color: T.gray400, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 220 }}>
            {source.url}
          </div>
        )}
      </div>

      {/* Type */}
      <span style={{ fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4, background: tc.bg, color: tc.color, display: 'inline-block', width: 'fit-content' }}>
        {source.source_type}
      </span>

      {/* Category */}
      <span style={{ color: T.gray500 }}>{source.category}</span>

      {/* Last Sync */}
      <div>
        <span style={{ fontSize: 12, color: source.sync_error ? T.red : T.gray400 }}>
          {source.sync_error ? '同步失败' : timeAgo(source.last_sync_at)}
        </span>
        {source.sync_error && <div style={{ fontSize: 11, color: T.red, marginTop: 1 }}>{source.sync_error}</div>}
        {syncResult && <div style={{ fontSize: 11, color: T.teal, marginTop: 1 }}>{syncResult}</div>}
      </div>

      {/* Weight */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }}
        title={`权重 ${source.weight}/5 — 影响精选加分：${source.weight > 3 ? '+' : ''}${(source.weight - 3) * 8} 分`}
      >
        {[1, 2, 3, 4, 5].map((w) => (
          <span key={w} onClick={() => onWeightChange?.(w)} style={{ fontSize: 11, color: w <= source.weight ? T.primary : T.gray200, transition: 'color 0.15s', userSelect: 'none' }}>
            ●
          </span>
        ))}
        <span style={{ fontSize: 10, color: T.gray400, marginLeft: 4 }}>
          {(source.weight - 3) * 8 > 0 ? '+' : ''}{(source.weight - 3) * 8}
        </span>
      </div>

      {/* Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: isActive ? T.teal : T.red, display: 'inline-block' }} />
        <span style={{ fontSize: 11, color: isActive ? T.teal : T.red }}>
          {source.enabled ? (source.status === 'active' ? '正常' : source.status) : '已禁用'}
        </span>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button onClick={onSync} disabled={syncing} style={{ padding: '4px 10px', fontSize: 11, fontWeight: 500, background: syncing ? T.gray100 : T.tealLight, color: syncing ? T.gray400 : T.teal, border: `1px solid ${syncing ? T.gray200 : T.tealBorder}`, borderRadius: 4, cursor: syncing ? 'wait' : 'pointer', transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 4 }}>
          {syncing ? <Spinner /> : null}
          {syncing ? '同步中' : '同步'}
        </button>
        <button onClick={onEdit} style={{ padding: '4px 10px', fontSize: 11, fontWeight: 500, background: '#EEF2FF', color: '#4F46E5', border: '1px solid #C7D2FE', borderRadius: 4, cursor: 'pointer', transition: 'all 0.15s' }}>
          编辑
        </button>
        <button onClick={onDelete} disabled={deleting} style={{ padding: '4px 10px', fontSize: 11, fontWeight: 500, background: 'transparent', color: deleting ? T.gray300 : T.red, border: 'none', borderRadius: 4, cursor: deleting ? 'wait' : 'pointer', transition: 'color 0.15s' }}>
          {deleting ? '删除中…' : '删除'}
        </button>
      </div>
    </div>
  );
}

export { Spinner };
