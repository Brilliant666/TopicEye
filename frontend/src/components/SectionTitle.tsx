'use client';

import React from 'react';

interface SectionTitleProps {
  children: React.ReactNode;
}

export default function SectionTitle({ children }: SectionTitleProps) {
  return (
    <h3 className="mb-3.5 border-b-2 border-gray-100 pb-2 text-sm font-semibold text-gray-800">
      {children}
    </h3>
  );
}
