'use client';

import React from 'react';

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

export function Panel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cx('min-w-0 rounded-lg border border-gray-200 bg-white', className)}>
      {children}
    </section>
  );
}

export function Toolbar({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx('flex flex-wrap items-center gap-2', className)}>
      {children}
    </div>
  );
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'success' | 'danger';

export function Button({
  children,
  className,
  variant = 'secondary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  const variantClass: Record<ButtonVariant, string> = {
    primary: 'border-primary bg-primary text-white hover:bg-primary-hover',
    secondary: 'border-gray-200 bg-white text-gray-700 hover:border-primary-border hover:text-primary',
    ghost: 'border-transparent bg-transparent text-gray-500 hover:bg-gray-100 hover:text-gray-800',
    success: 'border-teal-border bg-teal-light text-teal hover:border-teal-border',
    danger: 'border-red-light bg-red-light text-red hover:border-red/30',
  };

  return (
    <button
      {...props}
      className={cx(
        'inline-flex min-h-9 items-center justify-center gap-1.5 rounded-sm border px-3 py-2 text-xs font-bold transition disabled:cursor-wait disabled:opacity-60',
        variantClass[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}

type BadgeTone = 'neutral' | 'primary' | 'teal' | 'amber' | 'purple' | 'red';

export function Badge({
  children,
  className,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  className?: string;
  tone?: BadgeTone;
}) {
  const toneClass: Record<BadgeTone, string> = {
    neutral: 'border-gray-200 bg-gray-100 text-gray-600',
    primary: 'border-primary-border bg-primary-light text-primary',
    teal: 'border-teal-border bg-teal-light text-teal',
    amber: 'border-amber-border bg-amber-light text-amber',
    purple: 'border-purple-border bg-purple-light text-purple',
    red: 'border-red-light bg-red-light text-red',
  };

  return (
    <span className={cx('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-black', toneClass[tone], className)}>
      {children}
    </span>
  );
}

export function Metric({
  label,
  value,
  icon,
  colorClass = 'text-gray-900',
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  colorClass?: string;
}) {
  return (
    <Panel className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-bold text-gray-500">{label}</div>
        {icon && <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-gray-50">{icon}</div>}
      </div>
      <div className={cx('font-mono text-2xl font-black leading-none', colorClass)}>{value}</div>
    </Panel>
  );
}
