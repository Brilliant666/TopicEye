/**
 * ContentAnalysisPanel — AI analysis detail overlay
 * Shows full analysis: summary, scores radar, key points, angles, titles
 */
'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';
import type { ContentAnalysis, RecommendLevel, ScoreBreakdown as ScoreBreakdownType } from '@/types';
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <RecommendTag level={level} />
          {analysis.adjusted_curation_score != null && (
            <CurationHero score={analysis.adjusted_curation_score} />
          )}
        </div>
      </div>

      {/* Score Breakdown — 6-dimension weighted bars */}
      {analysis.score_breakdown && (
        <Section title="精选分构成">
          <ScoreBreakdownChart breakdown={analysis.score_breakdown} />
        </Section>
      )}

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
    '适合蹭热点': { bg: '#fee2e2', color: '#dc2626' },
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

// ── Curation Hero Score ──

function CurationHero({ score }: { score: number }) {
  const rounded = Math.round(score);
  let color: string = T.gray500;
  if (rounded >= 85) color = '#16a34a';
  else if (rounded >= 70) color = '#2563eb';
  else if (rounded >= 55) color = '#d97706';
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
      <span style={{ fontSize: 28, fontWeight: 800, color, fontFamily: T.mono, lineHeight: 1 }}>
        {rounded}
      </span>
      <span style={{ fontSize: 11, color: T.gray400, fontWeight: 500 }}>精选分</span>
    </div>
  );
}

// ── Score Breakdown Chart ──

const DIMENSION_LABELS: Record<string, { label: string; color: string }> = {
  info_density: { label: '信息密度', color: '#3b82f6' },
  actionability: { label: '可操作性', color: '#8b5cf6' },
  creator_value: { label: '创作者价值', color: '#6366f1' },
  viral_potential: { label: '爆文潜力', color: '#ef4444' },
  source_authority: { label: '来源权威', color: '#f59e0b' },
  freshness: { label: '时效新鲜', color: '#10b981' },
};

function ScoreBreakdownChart({ breakdown }: { breakdown: ScoreBreakdownType }) {
  const dims = breakdown.dimension_scores || {};
  const factors = [
    { label: '来源加权', value: breakdown.source_bonus, max: 20, color: '#f59e0b' },
    { label: '时效衰减', value: breakdown.time_decay * 100, max: 100, color: '#10b981', suffix: '%' },
    { label: '多样性', value: breakdown.diversity_factor * 100, max: 100, color: '#6366f1', suffix: '%' },
  ];

  return (
    <div>
      {/* 6-dimension weighted contribution bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
        {Object.entries(DIMENSION_LABELS).map(([key, meta]) => {
          const raw = dims[key] || 0;
          // dimension_scores are already weighted (value * weight), max ≈ 25
          const pct = Math.min(100, (raw / 25) * 100);
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 12, color: T.gray600, width: 72, flexShrink: 0, textAlign: 'right' }}>
                {meta.label}
              </span>
              <div style={{ flex: 1, height: 8, borderRadius: 4, background: T.gray100, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: meta.color,
                    borderRadius: 4,
                    transition: 'width 0.6s ease',
                  }}
                />
              </div>
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.gray500, width: 32, textAlign: 'right' }}>
                {raw.toFixed(1)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Adjustment factors */}
      <div style={{
        display: 'flex', gap: 16, padding: '10px 14px',
        background: T.gray50, borderRadius: T.radius,
        border: `1px solid ${T.gray100}`,
      }}>
        {factors.map((f) => (
          <div key={f.label} style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: T.mono, color: f.color }}>
              {f.suffix ? `${Math.round(f.value)}${f.suffix}` : (f.value > 0 ? `+${f.value.toFixed(0)}` : f.value.toFixed(0))}
            </div>
            <div style={{ fontSize: 10, color: T.gray400, marginTop: 2 }}>{f.label}</div>
          </div>
        ))}
      </div>

      {/* Final score */}
      <div style={{
        marginTop: 12, padding: '12px 16px',
        background: 'linear-gradient(135deg, #eff6ff, #f0fdf4)',
        borderRadius: T.radius,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: 13, color: T.gray600, fontWeight: 500 }}>最终精选分</span>
        <span style={{ fontSize: 22, fontWeight: 800, fontFamily: T.mono, color: T.primary }}>
          {breakdown.final_score.toFixed(1)}
        </span>
      </div>
    </div>
  );
}
