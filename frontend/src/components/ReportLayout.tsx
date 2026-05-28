'use client';

import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { cx } from '@/components/ui';

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
    <div className="border-b border-gray-100 px-5 pb-3 pt-5">
      <div className="flex items-center gap-2">
        <Icon size={17} className="text-gray-700" strokeWidth={2} />
        <span className="text-sm font-bold text-gray-900">{title}</span>
      </div>
      <p className="mt-1 text-[11px] text-gray-400">{countText}</p>
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
      type="button"
      onClick={onClick}
      className={cx(
        'flex w-full items-center gap-2 rounded-sm border px-3 py-2 text-left text-[13px] font-bold transition',
        active ? 'border-primary bg-primary text-white' : 'border-primary-border bg-primary-light text-primary hover:border-primary',
      )}
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
  return (
    <span
      className={cx(
        'rounded-xs border px-2 py-0.5 text-[10px] font-bold',
        tone === 'history'
          ? 'border-purple-border bg-purple-light text-purple'
          : 'border-gray-200 bg-gray-100 text-gray-600',
      )}
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
      type="button"
      onClick={onClick}
      disabled={loading}
      className="inline-flex min-h-9 items-center justify-center gap-2 rounded-sm bg-primary px-4 py-2 text-[13px] font-bold text-white transition hover:bg-primary-hover disabled:cursor-wait disabled:bg-gray-100 disabled:text-gray-400"
    >
      <Icon size={14} strokeWidth={2.2} />
      {loading ? loadingText : children}
    </button>
  );
}

export function ReportSectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="mb-3.5 flex items-center gap-2">
      <Icon size={16} className="text-gray-600" strokeWidth={2} />
      <h2 className="m-0 text-base font-bold text-gray-900">{title}</h2>
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
  const color = tone === 'error' ? 'text-red' : 'text-gray-400';

  return (
    <div className={cx('grid min-h-[360px] place-items-center p-10 text-center text-sm', color)}>
      <div>
        <Icon size={30} className={cx('mx-auto mb-3', color)} strokeWidth={1.9} />
        <div>{children}</div>
        {action && <div className="mt-4">{action}</div>}
      </div>
    </div>
  );
}

export function PlatformHeading({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <div className="mb-2.5 flex items-center gap-2 text-sm font-bold text-gray-900">
      <Icon size={15} className="text-gray-500" strokeWidth={2} />
      {label}
    </div>
  );
}

export function ReportFooterStat({ icon: Icon, children }: { icon: LucideIcon; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon size={13} className="text-gray-400" strokeWidth={2} />
      {children}
    </span>
  );
}
