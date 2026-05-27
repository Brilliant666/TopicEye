'use client';

import React, { useState } from 'react';
import { Check, Clipboard, MessageSquare, MousePointer2, Music2, Paperclip, Pin, Video } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import { formatPlanText } from '@/lib/utils';

interface Scene {
  seq: number;
  seconds: number;
  visual: string;
  narration: string;
}

interface OutlineSection {
  section: number;
  heading: string;
  points?: string[];
  evidence?: string;
}

export interface CreationPlan {
  titles?: string[];
  tone?: string;
  cover_slogan?: string;
  structure?: { hook?: string; points?: string[]; cta?: string };
  tags?: string[];
  hook?: string;
  scenes?: Scene[];
  total_seconds?: number;
  bgm_suggestion?: string;
  outline?: OutlineSection[];
  word_count_estimate?: number;
  key_quote?: string;
  closing?: string;
  _meta?: { platform: string; platform_name: string; content_id: number };
  [key: string]: unknown;
}

interface CreationPlanDisplayProps {
  plan: CreationPlan;
  platform: string;
}

export default function CreationPlanDisplay({ plan, platform }: CreationPlanDisplayProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = formatPlanText(plan as Record<string, unknown>);
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Copy button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleCopy}
          style={{
            fontSize: 11, fontWeight: 600, padding: '4px 12px',
            background: copied ? '#10B981' : T.gray100,
            color: copied ? T.white : T.gray600,
            border: 'none', borderRadius: 4, cursor: 'pointer',
          }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            {copied ? <Check size={12} strokeWidth={2.4} /> : <Clipboard size={12} strokeWidth={2.2} />}
            {copied ? '已复制' : '复制全文'}
          </span>
        </button>
      </div>

      {/* Titles */}
      {plan.titles && plan.titles.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>备选标题</div>
          {plan.titles.map((t: string, i: number) => (
            <div key={i} style={{
              fontSize: 14, fontWeight: 600, color: T.gray900, lineHeight: 1.6,
              padding: '8px 12px', marginBottom: 4,
              background: i === 0 ? `${T.primary}08` : T.gray50,
              borderRadius: 6, borderLeft: i === 0 ? `3px solid ${T.primary}` : '3px solid transparent',
            }}>
              {t}
            </div>
          ))}
        </div>
      )}

      {/* Platform-specific: xiaohongshu */}
      {platform === 'xiaohongshu' && plan.structure && (
        <>
          {plan.cover_slogan && (
            <div style={{ padding: '8px 12px', background: '#FF6B3510', borderRadius: 6, borderLeft: '3px solid #FF6B35' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#FF6B35' }}>封面文案：</span>
              <span style={{ fontSize: 13, color: T.gray700 }}> {plan.cover_slogan}</span>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 6 }}>正文结构</div>
            {plan.structure.hook && (
              <div style={{ display: 'flex', gap: 7, fontSize: 13, color: T.gray700, lineHeight: 1.6, marginBottom: 6, paddingLeft: 12, borderLeft: `2px solid ${T.primary}` }}>
                <MousePointer2 size={14} color={T.primary} strokeWidth={2} style={{ marginTop: 3, flexShrink: 0 }} />
                <span><b>Hook:</b> {plan.structure.hook}</span>
              </div>
            )}
            {plan.structure.points?.map((p: string, i: number) => (
              <div key={i} style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6, marginBottom: 4, paddingLeft: 12, borderLeft: '2px solid #10B981' }}>
                {p}
              </div>
            ))}
            {plan.structure.cta && (
              <div style={{ display: 'flex', gap: 7, fontSize: 13, color: T.gray700, lineHeight: 1.6, paddingLeft: 12, borderLeft: '2px solid #F59E0B' }}>
                <MessageSquare size={14} color="#F59E0B" strokeWidth={2} style={{ marginTop: 3, flexShrink: 0 }} />
                <span><b>互动引导:</b> {plan.structure.cta}</span>
              </div>
            )}
          </div>
          {plan.tags && plan.tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {plan.tags.map((tag: string) => (
                <span key={tag} style={{ fontSize: 11, color: T.primary, background: `${T.primary}10`, padding: '2px 10px', borderRadius: 12 }}>#{tag}</span>
              ))}
            </div>
          )}
        </>
      )}

      {/* Platform-specific: short_video */}
      {platform === 'short_video' && plan.scenes && (
        <>
          {plan.hook && (
            <div style={{ padding: '10px 14px', background: '#EF444410', borderRadius: 6, borderLeft: '3px solid #EF4444' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#EF4444' }}>前3秒Hook：</span>
              <span style={{ fontSize: 13, color: T.gray700 }}> {plan.hook}</span>
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 8 }}>分镜头脚本（共{plan.total_seconds || 60}秒）</div>
            {plan.scenes.map((scene: Scene, i: number) => (
              <div key={i} style={{ padding: '10px 14px', marginBottom: 6, background: T.gray50, borderRadius: 6, borderLeft: `3px solid ${T.primary}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: T.primary }}>镜头 {scene.seq}</span>
                  <span style={{ fontSize: 11, color: T.gray400 }}>{scene.seconds}s</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: T.gray500, marginBottom: 2 }}>
                  <Video size={13} strokeWidth={2} />
                  {scene.visual}
                </div>
                <div style={{ fontSize: 13, color: T.gray700 }}>{scene.narration}</div>
              </div>
            ))}
          </div>
          {plan.bgm_suggestion && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: T.gray500, padding: '8px 12px', background: T.gray50, borderRadius: 6 }}>
              <Music2 size={13} strokeWidth={2} />
              BGM建议：{plan.bgm_suggestion}
            </div>
          )}
        </>
      )}

      {/* Platform-specific: wechat */}
      {platform === 'wechat' && plan.outline && (
        <>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.gray500, marginBottom: 8 }}>
              文章大纲（约{plan.word_count_estimate || 2000}字）
            </div>
            {plan.outline.map((section: OutlineSection, i: number) => (
              <div key={i} style={{ padding: '12px 14px', marginBottom: 6, background: T.gray50, borderRadius: 6, borderLeft: `3px solid ${i === 0 ? '#FF6B35' : T.primary}` }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.gray900, marginBottom: 4 }}>
                  {section.section}. {section.heading}
                </div>
                {section.points?.map((p: string, j: number) => (
                  <div key={j} style={{ fontSize: 12, color: T.gray600, lineHeight: 1.6, paddingLeft: 8 }}>• {p}</div>
                ))}
                {section.evidence && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: T.gray400, marginTop: 4, fontStyle: 'italic' }}>
                    <Paperclip size={12} strokeWidth={2} />
                    {section.evidence}
                  </div>
                )}
              </div>
            ))}
          </div>
          {plan.key_quote && (
            <div style={{ padding: '12px 16px', background: `${T.primary}08`, borderRadius: 6, borderLeft: `3px solid ${T.primary}` }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.primary, marginBottom: 4 }}>金句</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, fontStyle: 'italic' }}>「{plan.key_quote}」</div>
            </div>
          )}
          {plan.closing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: T.gray600, padding: '10px 14px', background: T.gray50, borderRadius: 6 }}>
              <Pin size={13} strokeWidth={2} />
              结尾：{plan.closing}
            </div>
          )}
        </>
      )}

      {plan.tone && (
        <div style={{ fontSize: 11, color: T.gray400, textAlign: 'center' }}>风格建议：{plan.tone}</div>
      )}
    </div>
  );
}
