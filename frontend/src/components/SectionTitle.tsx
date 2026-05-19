'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';

interface SectionTitleProps {
  children: React.ReactNode;
}

export default function SectionTitle({ children }: SectionTitleProps) {
  return (
    <h3
      style={{
        fontSize: 14,
        fontWeight: 600,
        color: T.gray800,
        marginBottom: 14,
        paddingBottom: 8,
        borderBottom: `2px solid ${T.gray100}`,
        letterSpacing: '0.02em',
      }}
    >
      {children}
    </h3>
  );
}
