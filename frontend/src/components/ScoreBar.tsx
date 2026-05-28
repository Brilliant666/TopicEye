'use client';

import React from 'react';
import { cx } from '@/components/ui';

interface ScoreBarProps {
  label: string;
  value: number;
  maxVal?: number;
}

export default function ScoreBar({ label, value, maxVal = 100 }: ScoreBarProps) {
  const pct = Math.min((value / maxVal) * 100, 100);
  const barColor = value >= 80 ? 'bg-primary' : value >= 60 ? 'bg-teal' : 'bg-gray-400';

  return (
    <div className="flex items-center gap-2">
      <span className="w-7 shrink-0 text-xs text-gray-500">
        {label}
      </span>
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-gray-200">
        <div
          className={cx('h-full rounded-full transition-[width] duration-700 ease-out', barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-[22px] text-right font-mono text-xs font-medium text-gray-700">
        {value}
      </span>
    </div>
  );
}
