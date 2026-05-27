'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Star } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import type { Topic } from '@/types';
import LevelBadge from './LevelBadge';
import PlatformTag from './PlatformTag';

interface TopicCardProps {
  topic: Topic;
  isFav: boolean;
  onToggleFav: (id: number) => void;
}

export default function TopicCard({ topic, isFav, onToggleFav }: TopicCardProps) {
  const [hovered, setHovered] = useState(false);
  const router = useRouter();

  return (
    <div
      onClick={() => router.push(`/topics/${topic.id}`)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: T.white,
        borderRadius: T.radius,
        padding: 24,
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: hovered
          ? '0 8px 24px rgba(0,0,0,0.08)'
          : '0 1px 3px rgba(0,0,0,0.04)',
        transform: hovered ? 'translateY(-2px)' : 'none',
        border: `1px solid ${hovered ? T.gray200 : T.gray100}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      {/* Header: level + categories */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <LevelBadge level={topic.recommendLevel} size="small" />
        {topic.categories.map((c) => (
          <span key={c} style={{ fontSize: 11, color: T.gray400, fontWeight: 500 }}>
            {c}
          </span>
        ))}
      </div>

      {/* Title */}
      <h3
        style={{
          fontSize: 16,
          fontWeight: 600,
          lineHeight: 1.5,
          color: T.gray900,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {topic.title}
      </h3>

      {/* Source + time */}
      <div style={{ fontSize: 12, color: T.gray400 }}>
        <span style={{ color: T.gray500, fontWeight: 500 }}>{topic.source}</span>
        <span style={{ margin: '0 6px' }}>·</span>
        <span>{topic.publishedAt}</span>
      </div>

      {/* Scores */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {/* Hot Score Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: T.gray500, width: 28, flexShrink: 0 }}>热度</span>
          <div
            style={{
              flex: 1,
              height: 4,
              background: T.gray200,
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${topic.hotScore}%`,
                height: '100%',
                borderRadius: 2,
                background: topic.hotScore >= 80 ? T.primary : T.teal,
                transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            />
          </div>
          <span
            style={{
              fontSize: 12,
              fontFamily: T.mono,
              fontWeight: 500,
              color: T.gray700,
              width: 22,
              textAlign: 'right',
            }}
          >
            {topic.hotScore}
          </span>
        </div>
        {/* Creator Score Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: T.gray500, width: 28, flexShrink: 0 }}>价值</span>
          <div
            style={{
              flex: 1,
              height: 4,
              background: T.gray200,
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${topic.creatorScore}%`,
                height: '100%',
                borderRadius: 2,
                background: topic.creatorScore >= 80 ? T.primary : T.teal,
                transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            />
          </div>
          <span
            style={{
              fontSize: 12,
              fontFamily: T.mono,
              fontWeight: 500,
              color: T.gray700,
              width: 22,
              textAlign: 'right',
            }}
          >
            {topic.creatorScore}
          </span>
        </div>
      </div>

      {/* Reason */}
      <p
        style={{
          fontSize: 13,
          lineHeight: 1.6,
          color: T.gray500,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {topic.reason}
      </p>

      {/* Footer: platforms + favorite */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 2,
        }}
      >
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {topic.platforms.map((p) => (
            <PlatformTag key={p} name={p} />
          ))}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleFav(topic.id);
          }}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 4,
            color: isFav ? T.primary : T.gray300,
            transition: 'color 0.15s',
            display: 'inline-flex',
            alignItems: 'center',
          }}
          title={isFav ? '取消收藏' : '收藏'}
        >
          <Star size={18} strokeWidth={2} fill={isFav ? T.primary : 'none'} />
        </button>
      </div>
    </div>
  );
}
