'use client';

import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export function ReportSidebarHeader({
  icon: Icon,
  title,
  countText,
}: {
  icon: LucideIcon;
  title: string;
  countText: string;
}) {
  return (
    <div style={{ padding: '20px 20px 12px', borderBottom: `1px solid ${T.gray100}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon size={17} color={T.gray700} strokeWidth={2} />
        <span style={{ fontSize: 14, fontWeight: 700, color: T.gray900 }}>{title}</span>
      </div>
      <p style={{ fontSize: 11, color: T.gray400, marginTop: 4 }}>{countText}</p>
    </div>
  );
}

export function CurrentPeriodButton({
  active,
  icon: Icon,
  children,
  onClick,
}: {
  active: boolean;
  icon: LucideIcon;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        fontSize: 13,
        fontWeight: 600,
        color: active ? T.white : T.primary,
        background: active ? T.primary : T.primaryLight,
        border: `1px solid ${active ? T.primary : T.primaryBorder}`,
        borderRadius: T.radiusSm,
        cursor: 'pointer',
        transition: 'all 0.15s',
        textAlign: 'left',
      }}
    >
      <Icon size={14} strokeWidth={2.2} />
      {children}
    </button>
  );
}

export function ReportBadge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'history';
}) {
  const color = tone === 'history' ? T.purple : T.gray600;
  const background = tone === 'history' ? T.purpleLight : T.gray100;
  const border = tone === 'history' ? T.purpleBorder : T.gray200;

  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        color,
        background,
        padding: '3px 9px',
        borderRadius: T.radiusXs,
        border: `1px solid ${border}`,
        letterSpacing: 0,
      }}
    >
      {children}
    </span>
  );
}

export function ReportActionButton({
  loading,
  icon: Icon,
  children,
  loadingText = '生成中...',
  onClick,
}: {
  loading?: boolean;
  icon: LucideIcon;
  children: React.ReactNode;
  loadingText?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 7,
        padding: '8px 16px',
        fontSize: 13,
        fontWeight: 600,
        background: loading ? T.gray100 : T.primary,
        color: loading ? T.gray400 : T.white,
        border: 'none',
        borderRadius: T.radiusSm,
        cursor: loading ? 'wait' : 'pointer',
        transition: 'all 0.15s',
      }}
    >
      <Icon size={14} strokeWidth={2.2} />
      {loading ? loadingText : children}
    </button>
  );
}

export function ReportSectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
      <Icon size={16} color={T.gray600} strokeWidth={2} />
      <h2 style={{ fontSize: 16, fontWeight: 700, color: T.gray900 }}>{title}</h2>
    </div>
  );
}

export function ReportStatusPanel({
  icon: Icon,
  tone = 'muted',
  children,
  action,
}: {
  icon: LucideIcon;
  tone?: 'muted' | 'error';
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  const color = tone === 'error' ? T.red : T.gray400;

  return (
    <div style={{ textAlign: 'center', padding: 80, color, fontSize: 14 }}>
      <Icon size={30} color={color} strokeWidth={1.9} style={{ marginBottom: 12 }} />
      <div>{children}</div>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function PlatformHeading({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14, fontWeight: 600, color: T.gray900, marginBottom: 10 }}>
      <Icon size={15} color={T.gray500} strokeWidth={2} />
      {label}
    </div>
  );
}

export function ReportFooterStat({ icon: Icon, children }: { icon: LucideIcon; children: React.ReactNode }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <Icon size={13} color={T.gray400} strokeWidth={2} />
      {children}
    </span>
  );
}
