'use client';

import React from 'react';
import { T, PLATFORM_COLOR_MAP } from '@/lib/design-tokens';

interface PlatformTagProps {
  name: string;
}

export default function PlatformTag({ name }: PlatformTagProps) {
  const c = PLATFORM_COLOR_MAP[name] || { bg: T.gray100, color: T.gray600 };

  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        fontSize: 11,
        fontWeight: 500,
        color: c.color,
        background: c.bg,
        borderRadius: 4,
      }}
    >
      {name}
    </span>
  );
}
