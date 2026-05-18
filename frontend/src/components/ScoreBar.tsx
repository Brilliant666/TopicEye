'use client';

import React from 'react';
import { T, LEVEL_CONFIG } from '@/lib/design-tokens';

interface ScoreBarProps {
  label: string;
  value: number;
  maxVal?: number;
}

export default function ScoreBar({ label, value, maxVal = 100 }: ScoreBarProps) {
  const pct = Math.min((value / maxVal) * 100, 100);
  const barColor = value >= 80 ? T.primary : value >= 60 ? T.teal : T.gray400;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: T.gray500, width: 28, flexShrink: 0 }}>
        {label}
      </span>
      <div
        style={{
          flex: 1,
          height: 4,
          background: T.gray200,
          borderRadius: 2,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 2,
            background: barColor,
            transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>
      <span
        style={{
          fontSize: 12,
          fontFamily: T.mono,
          fontWeight: 500,
          color: T.gray700,
          width: 22,
          textAlign: 'right',
        }}
      >
        {value}
      </span>
    </div>
  );
}
