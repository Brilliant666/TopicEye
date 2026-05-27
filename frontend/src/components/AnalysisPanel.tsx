'use client';

import React, { useState } from 'react';
import { BookOpen, Loader2, PenLine, Video, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import { creationApi } from '@/lib/api';
import type { ContentAnalysis } from '@/types';
import CreationPlanDisplay from '@/components/CreationPlanDisplay';

interface AnalysisPanelProps {
  analysis: ContentAnalysis & { _content_id?: number };
  onClose: () => void;
}

export default function AnalysisPanel({ analysis, onClose }: AnalysisPanelProps) {
  const contentId = analysis.content_id || 0;
  const [creationPlan, setCreationPlan] = useState<Record<string, unknown> | null>(null);
  const [generating, setGenerating] = useState(false);
  const [activePlatform, setActivePlatform] = useState<string | null>(null);
  const platforms: Array<{ id: string; label: string; icon: LucideIcon }> = [
    { id: 'xiaohongshu', label: '小红书图文', icon: BookOpen },
    { id: 'short_video', label: '短视频脚本', icon: Video },
  ];

  const handleGenerate = async (platform: string) => {
    if (!contentId) return;
    setActivePlatform(platform);
    setGenerating(true);
    try {
      const plan = await creationApi.generatePlan(contentId, platform);
      setCreationPlan(plan);
    } catch (err) {
      console.error('Failed to generate plan:', err);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.2)', zIndex: 999 }} />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 520, maxWidth: '90vw',
        background: T.white, boxShadow: '-4px 0 24px rgba(0,0,0,0.1)', zIndex: 1000,
        overflowY: 'auto', padding: 32,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: T.gray900 }}>AI 分析报告</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.gray400, padding: 4 }} title="关闭">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 12 }}>精选评分</h3>
          {[
            { label: '精选分', value: analysis.curation_score || 0, color: '#FF6B35' },
            { label: '信息密度', value: analysis.info_density || 0, color: '#8B5CF6' },
            { label: '可操作性', value: analysis.actionability || 0, color: '#3B82F6' },
            { label: '来源权威', value: analysis.source_weight || 0, color: '#10B981' },
          ].map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: T.gray500, width: 64 }}>{s.label}</span>
              <div style={{ flex: 1, height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${s.value}%`, height: '100%', background: s.color, borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: T.gray700, width: 24, textAlign: 'right' }}>{Math.round(s.value)}</span>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 12 }}>多维评分</h3>
          {[
            { label: '质量', value: analysis.quality_score, color: '#10B981' },
            { label: '热度', value: analysis.hot_score, color: '#EF4444' },
            { label: '新鲜度', value: analysis.freshness_score, color: '#3B82F6' },
            { label: '创作价值', value: analysis.creator_score, color: T.primary },
            { label: '爆文潜力', value: analysis.viral_score, color: '#F59E0B' },
            { label: '风险', value: analysis.risk_score, color: '#6B7280' },
          ].map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: T.gray500, width: 64 }}>{s.label}</span>
              <div style={{ flex: 1, height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${s.value}%`, height: '100%', background: s.color, borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: T.gray700, width: 24, textAlign: 'right' }}>{Math.round(s.value)}</span>
            </div>
          ))}
        </div>

        {analysis.summary && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>内容摘要</h3>
            <p style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7 }}>{analysis.summary}</p>
          </div>
        )}
        {analysis.key_points != null && analysis.key_points.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>核心观点</h3>
            {analysis.key_points.map((point, i) => (
              <div key={i} style={{ marginBottom: 8, paddingLeft: 12, borderLeft: `3px solid ${T.primary}` }}>
                <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{point}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.creator_angles != null && analysis.creator_angles.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>创作角度</h3>
            {analysis.creator_angles.map((angle, i) => (
              <div key={i} style={{ marginBottom: 8, paddingLeft: 12, borderLeft: '3px solid #10B981' }}>
                <span style={{ fontSize: 13, color: T.gray600, lineHeight: 1.6 }}>{angle}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.title_suggestions != null && analysis.title_suggestions.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginBottom: 8 }}>建议标题</h3>
            {analysis.title_suggestions.map((title, i) => (
              <div key={i} style={{ fontSize: 13, color: T.gray600, lineHeight: 1.7, marginBottom: 6 }}>
                <span style={{ color: T.primary, fontWeight: 600 }}>{i + 1}.</span> {title}
              </div>
            ))}
          </div>
        )}

        {/* 创作方案生成 */}
        <div style={{
          marginTop: 28, padding: '20px', background: `linear-gradient(135deg, ${T.primary}06, #8B5CF606)`,
          borderRadius: T.radius, border: `1px solid ${T.primary}20`,
        }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14, fontWeight: 700, color: T.gray900, marginBottom: 4 }}>
            <PenLine size={15} strokeWidth={2} />
            生成创作方案
          </h3>
          <p style={{ fontSize: 12, color: T.gray500, marginBottom: 14 }}>基于该内容生成平台专属创作方案</p>

          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {platforms.map((p) => {
              const Icon = p.icon;
              return (
                <button
                  key={p.id}
                  onClick={() => handleGenerate(p.id)}
                  disabled={generating}
                  style={{
                    flex: 1, padding: '10px 8px', fontSize: 12, fontWeight: 600,
                    background: activePlatform === p.id && creationPlan ? T.primary : T.white,
                    color: activePlatform === p.id && creationPlan ? T.white : T.gray700,
                    border: `1px solid ${activePlatform === p.id && creationPlan ? T.primary : T.gray200}`,
                    borderRadius: T.radiusSm, cursor: generating ? 'wait' : 'pointer',
                    transition: 'all 0.15s',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  }}
                >
                  <Icon size={14} strokeWidth={2} />
                  {p.label}
                </button>
              );
            })}
          </div>

          {generating && (
            <div style={{ textAlign: 'center', padding: 24, color: T.gray400, fontSize: 13 }}>
              <Loader2 size={20} strokeWidth={2} style={{ marginBottom: 8, animation: 'pulse 1.5s infinite' }} />
              创作方案生成中...
            </div>
          )}

          {creationPlan && !generating && (
            <CreationPlanDisplay plan={creationPlan} platform={activePlatform || ''} />
          )}
        </div>
      </div>
    </>
  );
}
