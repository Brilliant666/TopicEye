'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';

interface CategoryChipProps {
  name: string;
  active: boolean;
  onClick: () => void;
}

export default function CategoryChip({ name, active, onClick }: CategoryChipProps) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 16px',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        color: active ? T.white : T.gray600,
        background: active ? T.primary : T.white,
        border: active ? 'none' : `1px solid ${T.gray200}`,
        borderRadius: 20,
        cursor: 'pointer',
        transition: 'all 0.2s ease',
      }}
    >
      {name}
    </button>
  );
}
