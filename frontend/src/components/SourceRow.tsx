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
  sort_order?: number;
  fetch_interval_minutes: number;
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

const INTERVAL_OPTIONS = [
  { value: 30, label: '30分钟' },
  { value: 60, label: '1小时' },
  { value: 120, label: '2小时' },
  { value: 360, label: '6小时' },
  { value: 720, label: '12小时' },
  { value: 1440, label: '1天' },
];

function formatInterval(minutes: number): string {
  const opt = INTERVAL_OPTIONS.find(o => o.value === minutes);
  return opt ? opt.label : `${minutes}分钟`;
}

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
  const [hovered, setHovered] = useState(false);
  const [intervalOpen, setIntervalOpen] = useState(false);
  const tc = typeColors[source.source_type] || { bg: T.gray100, color: T.gray600 };
  const isActive = source.status === 'active' && source.enabled;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setIntervalOpen(false); }}
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr 1fr 0.8fr 1.5fr',
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

      {/* Interval selector */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setIntervalOpen((v) => !v)}
          style={{
            padding: '3px 8px',
            fontSize: 11,
            background: intervalOpen ? T.primaryLight : T.gray100,
            color: intervalOpen ? T.primary : T.gray600,
            border: `1px solid ${intervalOpen ? T.primaryBorder : T.gray200}`,
            borderRadius: 4,
            cursor: 'pointer',
            transition: 'all 0.15s',
            whiteSpace: 'nowrap',
          }}
          title="点击修改采集频率"
        >
          {formatInterval(source.fetch_interval_minutes)}
          <span style={{ marginLeft: 4, fontSize: 10, opacity: 0.7 }}>▼</span>
        </button>
        {intervalOpen && (
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            zIndex: 100,
            background: T.white,
            border: `1px solid ${T.gray200}`,
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
            padding: '4px',
            minWidth: 90,
          }}>
            {INTERVAL_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                onClick={() => {
                  onIntervalChange?.(opt.value);
                  setIntervalOpen(false);
                }}
                style={{
                  padding: '6px 10px',
                  fontSize: 12,
                  borderRadius: 4,
                  cursor: 'pointer',
                  color: opt.value === source.fetch_interval_minutes ? T.primary : T.gray700,
                  background: opt.value === source.fetch_interval_minutes ? T.primaryLight : 'transparent',
                  fontWeight: opt.value === source.fetch_interval_minutes ? 600 : 400,
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => { if (opt.value !== source.fetch_interval_minutes) e.currentTarget.style.background = T.gray50; }}
                onMouseLeave={(e) => { if (opt.value !== source.fetch_interval_minutes) e.currentTarget.style.background = 'transparent'; }}
              >
                {opt.label}
              </div>
            ))}
          </div>
        )}
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
