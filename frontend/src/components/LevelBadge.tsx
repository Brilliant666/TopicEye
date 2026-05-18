'use client';

import React from 'react';
import { LEVEL_CONFIG } from '@/lib/design-tokens';
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
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: isSmall ? '2px 8px' : '4px 12px',
        fontSize: isSmall ? 11 : 12,
        fontWeight: 600,
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        borderRadius: 20,
        whiteSpace: 'nowrap',
        letterSpacing: '0.02em',
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: cfg.dot,
          flexShrink: 0,
        }}
      />
      {level}
    </span>
  );
}
