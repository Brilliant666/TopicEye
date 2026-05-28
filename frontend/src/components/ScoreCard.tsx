'use client';

import React from 'react';
import { cx } from '@/components/ui';

interface ScoreCardProps {
  label: string;
  value: number;
  desc: string;
  isRisk?: boolean;
}

export default function ScoreCard({ label, value, desc, isRisk }: ScoreCardProps) {
  const color = isRisk
    ? value > 70
      ? 'text-red'
      : value > 50
        ? 'text-amber'
        : 'text-teal'
    : value >= 80
      ? 'text-primary'
      : value >= 60
        ? 'text-teal'
        : 'text-gray-400';

  return (
    <div className="text-center">
      <div className={cx('font-mono text-[32px] font-bold leading-none', color)}>
        {Math.round(value)}
      </div>
      <div className="mt-1.5 text-[13px] font-semibold text-gray-700">{label}</div>
      <div className="mt-0.5 text-[11px] text-gray-400">{desc}</div>
    </div>
  );
}
