'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';
import LevelBadge from '@/components/LevelBadge';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';

interface TopicHeaderCardProps {
  item: ContentItem;
  analysis: ContentAnalysis | null;
  level: RecommendLevel;
  tags: string[];
  isFav: boolean;
  onToggleFavorite: () => void;
  timeAgoStr: string;
}

export default function TopicHeaderCard({
  item,
  analysis,
  level,
  tags,
  isFav,
  onToggleFavorite,
  timeAgoStr,
}: TopicHeaderCardProps) {
  return (
    <div
      style={{
        background: T.white,
        borderRadius: T.radius,
        padding: 32,
        marginBottom: 20,
        border: `1px solid ${T.gray100}`,
      }}
    >
      {/* Level + Tags */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginBottom: 16,
          flexWrap: 'wrap',
        }}
      >
        <LevelBadge level={level} />
        {tags.map((c) => (
          <span
            key={c}
            style={{
              fontSize: 12,
              color: T.gray500,
              fontWeight: 500,
              background: T.gray100,
              padding: '2px 8px',
              borderRadius: 4,
            }}
          >
            {c}
          </span>
        ))}
      </div>

      {/* Title */}
      <h1
        style={{
          fontSize: 24,
          fontWeight: 700,
          lineHeight: 1.5,
          color: T.gray900,
          marginBottom: 12,
        }}
      >
        {item.title}
      </h1>

      {/* Meta */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13, color: T.gray400, flexWrap: 'wrap' }}>
        {item.source_name && (
          <span>
            <b style={{ color: T.gray600 }}>{item.source_name}</b>
          </span>
        )}
        {timeAgoStr && <span>{timeAgoStr}</span>}
        <span style={{ color: T.gray300 }}>|</span>
        {item.source_type && <span>{item.source_type}</span>}
        {item.author && (
          <>
            <span style={{ color: T.gray300 }}>|</span>
            <span>{item.author}</span>
          </>
        )}
      </div>

      {/* Action bar */}
      <div style={{ marginTop: 20, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button
          onClick={onToggleFavorite}
          style={{
            padding: '8px 20px',
            fontSize: 13,
            fontWeight: 500,
            background: isFav ? T.primaryLight : T.gray100,
            color: isFav ? T.primary : T.gray600,
            border: `1px solid ${isFav ? T.primaryBorder : T.gray200}`,
            borderRadius: T.radiusSm,
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {isFav ? '★ 已收藏' : '☆ 收藏选题'}
        </button>

        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: '8px 20px',
              fontSize: 13,
              fontWeight: 500,
              background: T.tealLight,
              color: T.teal,
              border: `1px solid ${T.tealBorder}`,
              borderRadius: T.radiusSm,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              transition: 'all 0.15s',
            }}
          >
            查看原文 ↗
          </a>
        )}
      </div>
    </div>
  );
}
