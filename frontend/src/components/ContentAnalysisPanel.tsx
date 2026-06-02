/**
 * ContentAnalysisPanel — AI analysis detail overlay
 * Shows full analysis: summary, scores radar, key points, angles, titles
 */
'use client';

import React from 'react';
import { X } from 'lucide-react';
import { Badge, cx } from '@/components/ui';
import type { ContentAnalysis, RecommendLevel, ScoreBreakdown as ScoreBreakdownType } from '@/types';
import { explainRecommendation } from '@/lib/recommendation';

interface Props {
  analysis: ContentAnalysis;
  onClose: () => void;
}

export default function ContentAnalysisPanel({ analysis, onClose }: Props) {
  const recommendation = explainRecommendation(analysis);
  const level = recommendation.level;

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
      className="fixed bottom-0 right-0 top-0 z-[1000] h-screen w-[480px] max-w-[90vw] animate-[slideInRight_0.25s_ease] overflow-y-auto bg-white px-7 py-8 shadow-[-4px_0_24px_rgba(0,0,0,0.1)]"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Close button */}
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 inline-flex cursor-pointer items-center border-0 bg-transparent text-gray-400 transition hover:text-gray-600"
        title="关闭"
      >
        <X size={20} strokeWidth={2} />
      </button>

      {/* Header */}
      <div className="mb-6">
        <h2 className="mb-3 text-lg font-bold text-gray-900">
          AI 分析报告
        </h2>
        <div className="flex items-center gap-3">
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

      <Section title="算法判断">
        <p className="m-0 text-[13px] leading-7 text-gray-700">
          {recommendation.reason}
        </p>
        {recommendation.signals.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {recommendation.signals.map((signal) => (
              <Badge key={signal} tone="neutral" className="rounded-xs px-2 py-0.5">
                {signal}
              </Badge>
            ))}
          </div>
        )}
      </Section>

      {/* Summary */}
      {analysis.summary && (
        <Section title="内容摘要">
          <p className="m-0 text-sm leading-8 text-gray-700">
            {analysis.summary}
          </p>
        </Section>
      )}

      {/* Score grid */}
      <Section title="多维评分">
        <div className="grid grid-cols-3 gap-3">
          {scores.map((s) => (
            <ScoreBar key={s.label} label={s.label} value={s.value} color={s.color} />
          ))}
        </div>
      </Section>

      {/* Key Points */}
      {analysis.key_points && analysis.key_points.length > 0 && (
        <Section title="核心观点">
          <ul className="m-0 pl-[18px]">
            {analysis.key_points.map((pt, i) => (
              <li key={i} className="mb-1 text-[13px] leading-7 text-gray-700">
                {pt}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Creator Angles */}
      {analysis.creator_angles && analysis.creator_angles.length > 0 && (
        <Section title="创作角度">
          <div className="flex flex-col gap-2">
            {analysis.creator_angles.map((angle, i) => (
              <div
                key={i}
                className="rounded-lg border-l-[3px] border-primary bg-gray-50 px-3.5 py-2.5 text-[13px] leading-7 text-gray-700"
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
          <div className="flex flex-col gap-1.5">
            {analysis.title_suggestions.map((t, i) => (
              <div
                key={i}
                className="rounded bg-teal-light px-3 py-2 text-[13px] text-gray-700"
              >
                <span className="mr-2 font-semibold text-teal">{i + 1}.</span>
                {t}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Recommended Reason */}
      {analysis.recommended_reason && (
        <Section title="推荐理由">
          <p className="m-0 text-[13px] leading-7 text-gray-700">
            {analysis.recommended_reason}
          </p>
        </Section>
      )}

      {/* Audience Emotion */}
      {analysis.audience_emotion && (
        <Section title="受众情绪">
          <p className="m-0 text-[13px] leading-7 text-gray-700">
            {analysis.audience_emotion}
          </p>
        </Section>
      )}

      {/* Footer */}
      <div className="mt-8 border-t border-gray-100 pt-4 text-[11px] text-gray-400">
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
    <div className="mb-6">
      <h3 className="mb-3 text-sm font-bold text-gray-800">
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
    <div className="text-center">
      <div
        className="font-mono text-[22px] font-bold leading-none"
        style={{ color }}
      >
        {pct}
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded bg-gray-100">
        <div
          style={{
            width: `${pct}%`,
            background: color,
          }}
          className="h-full rounded transition-[width] duration-500"
        />
      </div>
      <div className="mt-1 text-[11px] text-gray-500">{label}</div>
    </div>
  );
}

// ── Recommend Tag ──

function RecommendTag({ level }: { level: RecommendLevel }) {
  const toneMap: Record<RecommendLevel, 'primary' | 'teal' | 'purple' | 'amber' | 'neutral'> = {
    '强烈建议写': 'primary',
    '值得观察': 'teal',
    '适合深挖': 'purple',
    '适合蹭热点': 'amber',
    '不建议追': 'neutral',
    '信号不足': 'neutral',
  };
  return <Badge tone={toneMap[level] || 'neutral'} className="rounded-xs px-4 py-1.5 text-sm">{level}</Badge>;
}

// ── Curation Hero Score ──

function CurationHero({ score }: { score: number }) {
  const rounded = Math.round(score);
  const colorClass = rounded >= 85 ? 'text-teal' : rounded >= 70 ? 'text-primary' : rounded >= 55 ? 'text-amber' : 'text-gray-500';
  return (
    <div className="flex items-baseline gap-1">
      <span className={cx('font-mono text-[28px] font-extrabold leading-none', colorClass)}>
        {rounded}
      </span>
      <span className="text-[11px] font-medium text-gray-400">精选分</span>
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
      <div className="mb-4 flex flex-col gap-2.5">
        {Object.entries(DIMENSION_LABELS).map(([key, meta]) => {
          const raw = dims[key] || 0;
          // dimension_scores are already weighted (value * weight), max ≈ 25
          const pct = Math.min(100, (raw / 25) * 100);
          return (
            <div key={key} className="flex items-center gap-2.5">
              <span className="w-[72px] shrink-0 text-right text-xs text-gray-600">
                {meta.label}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-gray-100">
                <div
                  style={{
                    width: `${pct}%`,
                    background: meta.color,
                  }}
                  className="h-full rounded transition-[width] duration-500"
                />
              </div>
              <span className="w-8 text-right font-mono text-[11px] text-gray-500">
                {raw.toFixed(1)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Adjustment factors */}
      <div className="flex gap-4 rounded-lg border border-gray-100 bg-gray-50 px-3.5 py-2.5">
        {factors.map((f) => (
          <div key={f.label} className="flex-1 text-center">
            <div className="font-mono text-base font-bold" style={{ color: f.color }}>
              {f.suffix ? `${Math.round(f.value)}${f.suffix}` : (f.value > 0 ? `+${f.value.toFixed(0)}` : f.value.toFixed(0))}
            </div>
            <div className="mt-0.5 text-[10px] text-gray-400">{f.label}</div>
          </div>
        ))}
      </div>

      {/* Final score */}
      <div className="mt-3 flex items-center justify-between rounded-lg bg-primary-light px-4 py-3">
        <span className="text-[13px] font-medium text-gray-600">最终精选分</span>
        <span className="font-mono text-[22px] font-extrabold text-primary">
          {breakdown.final_score.toFixed(1)}
        </span>
      </div>
    </div>
  );
}
