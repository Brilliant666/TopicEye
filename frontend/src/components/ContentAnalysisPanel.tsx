/**
 * ContentAnalysisPanel — AI analysis detail overlay
 * Shows full analysis: summary, scores radar, key points, angles, titles
 */
'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';
import type { ContentAnalysis, RecommendLevel } from '@/types';
import { getRecommendLevel } from '@/types';

interface Props {
  analysis: ContentAnalysis;
  onClose: () => void;
}

export default function ContentAnalysisPanel({ analysis, onClose }: Props) {
  const level = getRecommendLevel(analysis);

  const scores = [
    { label: '质量', value: analysis.quality_score, color: '#3498db' },
    { label: '热度', value: analysis.hot_score, color: '#e67e22' },
    { label: '新鲜度', value: analysis.freshness_score, color: '#2ecc71' },
    { label: '创作价值', value: analysis.creator_score, color: '#9b59b6' },
    { label: '爆文潜力', value: analysis.viral_score, color: '#e74c3c' },
    { label: '风险', value: analysis.risk_score, color: '#95a5a6' },
  ];

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 480,
        height: '100vh',
        background: T.white,
        boxShadow: '-4px 0 24px rgba(0,0,0,0.1)',
        zIndex: 1000,
        overflowY: 'auto',
        padding: '32px 28px',
        animation: 'slideInRight 0.25s ease',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        style={{
          position: 'absolute',
          top: 16,
          right: 16,
          background: 'none',
          border: 'none',
          fontSize: 22,
          cursor: 'pointer',
          color: T.gray400,
          lineHeight: 1,
        }}
      >
        ✕
      </button>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: T.gray900, marginBottom: 12 }}>
          AI 分析报告
        </h2>
        <RecommendTag level={level} />
      </div>

      {/* Summary */}
      {analysis.summary && (
        <Section title="内容摘要">
          <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray700, margin: 0 }}>
            {analysis.summary}
          </p>
        </Section>
      )}

      {/* Score grid */}
      <Section title="多维评分">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          {scores.map((s) => (
            <ScoreBar key={s.label} label={s.label} value={s.value} color={s.color} />
          ))}
        </div>
      </Section>

      {/* Key Points */}
      {analysis.key_points && analysis.key_points.length > 0 && (
        <Section title="核心观点">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {analysis.key_points.map((pt, i) => (
              <li key={i} style={{ fontSize: 13, lineHeight: 1.8, color: T.gray700, marginBottom: 4 }}>
                {pt}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Creator Angles */}
      {analysis.creator_angles && analysis.creator_angles.length > 0 && (
        <Section title="创作角度">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {analysis.creator_angles.map((angle, i) => (
              <div
                key={i}
                style={{
                  padding: '10px 14px',
                  background: T.gray50,
                  borderRadius: T.radius,
                  fontSize: 13,
                  lineHeight: 1.7,
                  color: T.gray700,
                  borderLeft: `3px solid ${T.primary}`,
                }}
              >
                {angle}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Title Suggestions */}
      {analysis.title_suggestions && analysis.title_suggestions.length > 0 && (
        <Section title="建议标题">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {analysis.title_suggestions.map((t, i) => (
              <div
                key={i}
                style={{
                  fontSize: 13,
                  color: T.gray700,
                  padding: '8px 12px',
                  background: T.tealLight,
                  borderRadius: 4,
                }}
              >
                <span style={{ fontWeight: 600, color: T.teal, marginRight: 8 }}>{i + 1}.</span>
                {t}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Recommended Reason */}
      {analysis.recommended_reason && (
        <Section title="推荐理由">
          <p style={{ fontSize: 13, lineHeight: 1.8, color: T.gray700, margin: 0 }}>
            {analysis.recommended_reason}
          </p>
        </Section>
      )}

      {/* Audience Emotion */}
      {analysis.audience_emotion && (
        <Section title="受众情绪">
          <p style={{ fontSize: 13, lineHeight: 1.8, color: T.gray700, margin: 0 }}>
            {analysis.audience_emotion}
          </p>
        </Section>
      )}

      {/* Footer */}
      <div style={{ marginTop: 32, paddingTop: 16, borderTop: `1px solid ${T.gray100}`, color: T.gray400, fontSize: 11 }}>
        分析时间：{new Date(analysis.created_at).toLocaleString('zh-CN')}
      </div>

      {/* CSS Animation */}
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

// ── Section ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, color: T.gray800, marginBottom: 12 }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

// ── Score Bar ──

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value);
  return (
    <div style={{ textAlign: 'center' }}>
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color,
          fontFamily: T.mono,
          lineHeight: 1,
        }}
      >
        {pct}
      </div>
      <div
        style={{
          height: 4,
          borderRadius: 2,
          background: T.gray100,
          marginTop: 6,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: color,
            borderRadius: 2,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
      <div style={{ fontSize: 11, color: T.gray500, marginTop: 4 }}>{label}</div>
    </div>
  );
}

// ── Recommend Tag ──

function RecommendTag({ level }: { level: RecommendLevel }) {
  const colorMap: Record<RecommendLevel, { bg: string; color: string }> = {
    '强烈建议写': { bg: '#dcfce7', color: '#16a34a' },
    '值得观察': { bg: '#dbeafe', color: '#2563eb' },
    '适合深挖': { bg: '#fef3c7', color: '#d97706' },
    '可蹭但谨慎': { bg: '#fee2e2', color: '#dc2626' },
    '不建议追': { bg: '#f3f4f6', color: '#9ca3af' },
  };
  const { bg, color } = colorMap[level] || { bg: '#f3f4f6', color: '#9ca3af' };
  return (
    <span
      style={{
        fontSize: 14,
        fontWeight: 700,
        color,
        background: bg,
        padding: '6px 16px',
        borderRadius: 6,
        display: 'inline-block',
      }}
    >
      {level}
    </span>
  );
}
