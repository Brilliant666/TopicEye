'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';

interface HeaderProps {
  title: string;
  subtitle?: string;
  date?: string;
  stats?: { label: string; value: number; color?: string }[];
}

export default function Header({ title, subtitle, date, stats }: HeaderProps) {
  return (
    <div style={{ marginBottom: 28, maxWidth: 820 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 6 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>{title}</h1>
        {date && <span style={{ fontSize: 14, color: T.gray400 }}>{date}</span>}
      </div>
      {subtitle && (
        <p style={{ fontSize: 13, color: T.gray400 }}>{subtitle}</p>
      )}
      {stats && stats.length > 0 && (
        <div style={{ display: 'flex', gap: 16, fontSize: 13, color: T.gray500 }}>
          {stats.map((s, i) => (
            <span key={i}>
              {s.label}{' '}
              <b style={{ color: s.color || T.primary, fontFamily: T.mono }}>{s.value}</b>{' '}
              条
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
