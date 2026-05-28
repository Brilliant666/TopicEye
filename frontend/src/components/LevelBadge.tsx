'use client';

import React from 'react';
import { cx } from '@/components/ui';
import type { RecommendLevel } from '@/types';

interface LevelBadgeProps {
  level: RecommendLevel | string;
  size?: 'normal' | 'small';
}

export default function LevelBadge({ level, size = 'normal' }: LevelBadgeProps) {
  const cfg = LEVEL_CONFIG[level] || LEVEL_CONFIG['不建议追'];
  const isSmall = size === 'small';

  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold',
        isSmall ? 'px-2 py-0.5 text-[11px]' : 'px-3 py-1 text-xs',
        cfg.bg,
        cfg.text,
        cfg.border,
      )}
    >
      <span className={cx('h-1.5 w-1.5 shrink-0 rounded-full', cfg.dot)} />
      {level}
    </span>
  );
}

const LEVEL_CONFIG: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  强烈建议写: { bg: 'bg-primary-light', text: 'text-primary', border: 'border-primary-border', dot: 'bg-primary' },
  值得观察: { bg: 'bg-teal-light', text: 'text-teal', border: 'border-teal-border', dot: 'bg-teal' },
  适合深挖: { bg: 'bg-purple-light', text: 'text-purple', border: 'border-purple-border', dot: 'bg-purple' },
  适合蹭热点: { bg: 'bg-amber-light', text: 'text-amber', border: 'border-amber-border', dot: 'bg-amber' },
  不建议追: { bg: 'bg-gray-100', text: 'text-gray-500', border: 'border-gray-300', dot: 'bg-gray-400' },
};
