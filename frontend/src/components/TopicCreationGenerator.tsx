'use client';

import React, { useState } from 'react';
import { BookOpen, FileText, PenLine, Video } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import SectionTitle from '@/components/SectionTitle';
import CreationPlanDisplay, { type CreationPlan } from '@/components/CreationPlanDisplay';

interface TopicCreationGeneratorProps {
  contentId: number;
}

export default function TopicCreationGenerator({ contentId }: TopicCreationGeneratorProps) {
  const [creationPlan, setCreationPlan] = useState<CreationPlan | null>(null);
  const [creating, setCreating] = useState(false);
  const [creatingPlatform, setCreatingPlatform] = useState<string | null>(null);
  const [creationError, setCreationError] = useState<string | null>(null);

  const platforms: Array<{ id: string; name: string; icon: LucideIcon }> = [
    { id: 'xiaohongshu', name: '小红书', icon: BookOpen },
    { id: 'wechat', name: '公众号', icon: FileText },
    { id: 'short_video', name: '短视频', icon: Video },
  ];

  const handleGeneratePlan = async (platform: string) => {
    if (!contentId) return;
    setCreating(true);
    setCreatingPlatform(platform);
    setCreationError(null);

    try {
      const { creationApi } = await import('@/lib/api');
      const result = await creationApi.generatePlan(contentId, platform) as CreationPlan & { _meta?: { platform: string } };
      setCreationPlan(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '生成失败';
      setCreationError(msg);
    } finally {
      setCreating(false);
      setCreatingPlatform(null);
    }
  };

  return (
    <div
      style={{
        background: T.white,
        borderRadius: T.radius,
        padding: 28,
        marginBottom: 20,
        border: `1px solid ${T.gray100}`,
      }}
    >
      <SectionTitle>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
          <PenLine size={15} strokeWidth={2} />
          生成创作方案
        </span>
      </SectionTitle>
      <p style={{ fontSize: 13, color: T.gray500, marginBottom: 16 }}>
        选择平台，基于此内容生成完整的创作方案
      </p>

      {/* Platform buttons */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {platforms.map((p) => {
          const Icon = p.icon;
          return (
            <button
              key={p.id}
              onClick={() => handleGeneratePlan(p.id)}
              disabled={creating}
              style={{
                padding: '10px 18px',
                fontSize: 13,
                fontWeight: 500,
                background: creatingPlatform === p.id ? T.primaryLight : T.gray50,
                color: creatingPlatform === p.id ? T.primary : T.gray700,
                border: `1px solid ${creatingPlatform === p.id ? T.primaryBorder : T.gray200}`,
                borderRadius: T.radiusSm,
                cursor: creating ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                transition: 'all 0.15s',
                opacity: creating && creatingPlatform !== p.id ? 0.5 : 1,
              }}
            >
              <Icon size={14} strokeWidth={2} />
              {creatingPlatform === p.id ? '生成中...' : p.name}
            </button>
          );
        })}
      </div>

      {/* Creation error */}
      {creationError && (
        <div
          style={{
            marginTop: 12,
            padding: '10px 14px',
            background: T.redLight,
            borderRadius: T.radiusSm,
            fontSize: 13,
            color: '#991B1B',
          }}
        >
          生成失败：{creationError}
        </div>
      )}

      {/* Creation plan result */}
      {creationPlan && (
        <div
          style={{
            marginTop: 16,
            padding: 20,
            background: T.gray50,
            borderRadius: T.radiusSm,
            border: `1px solid ${T.gray100}`,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: T.gray800, marginBottom: 12 }}>
            创作方案
          </div>
          <CreationPlanDisplay plan={creationPlan} platform={creationPlan._meta?.platform ?? creatingPlatform ?? ''} />
        </div>
      )}
    </div>
  );
}
