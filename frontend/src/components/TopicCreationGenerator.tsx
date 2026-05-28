'use client';

import React, { useState } from 'react';
import { BookOpen, FileText, PenLine, Video } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import SectionTitle from '@/components/SectionTitle';
import { Button, Panel, Toolbar, cx } from '@/components/ui';
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
    <Panel className="mb-5 p-7">
      <SectionTitle>
        <span className="inline-flex items-center gap-2">
          <PenLine size={15} strokeWidth={2} />
          生成创作方案
        </span>
      </SectionTitle>
      <p className="mb-4 text-[13px] text-gray-500">
        选择平台，基于此内容生成完整的创作方案
      </p>

      {/* Platform buttons */}
      <Toolbar className="gap-2.5">
        {platforms.map((p) => {
          const Icon = p.icon;
          const active = creatingPlatform === p.id;
          return (
            <Button
              key={p.id}
              type="button"
              onClick={() => handleGeneratePlan(p.id)}
              disabled={creating}
              variant={active ? 'primary' : 'secondary'}
              className={cx('px-[18px] py-2.5 text-[13px] font-medium', creating && !active && 'opacity-50')}
            >
              <Icon size={14} strokeWidth={2} />
              {active ? '生成中...' : p.name}
            </Button>
          );
        })}
      </Toolbar>

      {/* Creation error */}
      {creationError && (
        <div className="mt-3 rounded-sm bg-red-light px-3.5 py-2.5 text-[13px] text-red">
          生成失败：{creationError}
        </div>
      )}

      {/* Creation plan result */}
      {creationPlan && (
        <Panel className="mt-4 bg-gray-50 p-5">
          <div className="mb-3 text-sm font-semibold text-gray-800">
            创作方案
          </div>
          <CreationPlanDisplay plan={creationPlan} platform={creationPlan._meta?.platform ?? creatingPlatform ?? ''} />
        </Panel>
      )}
    </Panel>
  );
}
