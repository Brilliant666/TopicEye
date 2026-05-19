'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';

interface ScoreCardProps {
  label: string;
  value: number;
  desc: string;
  isRisk?: boolean;
}

export default function ScoreCard({ label, value, desc, isRisk }: ScoreCardProps) {
  const color = isRisk
    ? value > 70
      ? T.red
      : value > 50
        ? T.amber
        : T.teal
    : value >= 80
      ? T.primary
      : value >= 60
        ? T.teal
        : T.gray400;

  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 32, fontWeight: 700, fontFamily: T.mono, color, lineHeight: 1 }}>
        {Math.round(value)}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginTop: 6 }}>{label}</div>
      <div style={{ fontSize: 11, color: T.gray400, marginTop: 2 }}>{desc}</div>
    </div>
  );
}
