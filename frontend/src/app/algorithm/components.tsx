'use client';

import React from 'react';
import {
  CheckCircle2,
  ExternalLink,
  Filter,
  GitBranch,
  Minus,
  Plus,
  RefreshCw,
  ShieldAlert,
  SlidersHorizontal,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import type { FeedbackType, ScoringFlowResponse, ScoringFlowSample } from '@/lib/api';

const STAGE_COLORS: Record<string, { color: string; bg: string; border: string }> = {
  candidates: { color: T.gray700, bg: T.gray50, border: T.gray200 },
  quality: { color: T.teal, bg: T.tealLight, border: T.tealBorder },
  risk: { color: T.amber, bg: T.amberLight, border: T.amberBorder },
  freshness: { color: '#3B82F6', bg: '#EFF6FF', border: '#BFDBFE' },
  diversity: { color: T.purple, bg: T.purpleLight, border: T.purpleBorder },
  selected: { color: T.primary, bg: T.primaryLight, border: T.primaryBorder },
};

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function fmt(value: number | undefined, digits = 1) {
  return Number(value ?? 0).toFixed(digits);
}

function Panel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, ...style }}>
      {children}
    </div>
  );
}

function MetricValue({ value, color }: { value: React.ReactNode; color: string }) {
  return (
    <div style={{ fontSize: 24, fontWeight: 800, fontFamily: T.mono, color }}>{value}</div>
  );
}

function FactorBar({ label, value, color }: { label: string; value: number; color: string }) {
  const width = Math.max(4, Math.min(100, value * 100));
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.gray500, marginBottom: 5 }}>
        <span>{label}</span>
        <span style={{ fontFamily: T.mono }}>{fmt(value, 2)}</span>
      </div>
      <div style={{ height: 7, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
        <div style={{ width: `${width}%`, height: '100%', background: color, borderRadius: 999 }} />
      </div>
    </div>
  );
}

function ProgressRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '76px 1fr 46px', alignItems: 'center', gap: 8 }}>
      <div style={{ fontSize: 12, color: T.gray500 }}>{label}</div>
      <div style={{ height: 8, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(3, Math.min(100, value))}%`, height: '100%', background: color }} />
      </div>
      <div style={{ fontSize: 11, color: T.gray600, fontFamily: T.mono, textAlign: 'right' }}>{fmt(value)}</div>
    </div>
  );
}

function FeedbackButton({
  icon,
  label,
  disabled,
  onClick,
  palette,
}: {
  icon: React.ReactNode;
  label: string;
  disabled: boolean;
  onClick: () => void;
  palette: { color: string; bg: string; border: string };
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        padding: '9px 10px',
        border: `1px solid ${palette.border}`,
        background: palette.bg,
        color: palette.color,
        borderRadius: T.radiusSm,
        fontSize: 12,
        fontWeight: 700,
        cursor: disabled ? 'wait' : 'pointer',
      }}
    >
      {icon} {label}
    </button>
  );
}

export function AlgorithmHeader({
  hours,
  loading,
  onHoursChange,
  onRefresh,
}: {
  hours: number;
  loading: boolean;
  onHoursChange: (hours: number) => void;
  onRefresh: () => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 18, marginBottom: 22 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <GitBranch size={22} color={T.primary} />
          <h1 style={{ fontSize: 25, fontWeight: 800, color: T.gray900 }}>算法流程</h1>
        </div>
        <p style={{ fontSize: 13, color: T.gray500, lineHeight: 1.6 }}>
          候选池、特征评分、质量/风险/时效/多样性路径和最终精选输出。
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {[24, 48, 168].map((h) => (
          <button
            key={h}
            onClick={() => onHoursChange(h)}
            style={{
              padding: '8px 12px',
              border: `1px solid ${hours === h ? T.primary : T.gray200}`,
              background: hours === h ? T.primaryLight : T.white,
              color: hours === h ? T.primary : T.gray600,
              borderRadius: T.radiusSm,
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {h === 168 ? '7天' : `${h}h`}
          </button>
        ))}
        <button
          onClick={onRefresh}
          disabled={loading}
          title="刷新"
          style={{
            width: 36,
            height: 36,
            borderRadius: T.radiusSm,
            border: `1px solid ${T.gray200}`,
            background: T.white,
            color: T.gray600,
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          <RefreshCw size={15} style={{ verticalAlign: 'middle' }} />
        </button>
      </div>
    </div>
  );
}

export function SummaryGrid({ data }: { data: ScoringFlowResponse }) {
  const cards: Array<{ label: string; value: React.ReactNode; icon: LucideIcon; color: string }> = [
    { label: '数据库候选', value: data.total, icon: SlidersHorizontal, color: T.gray800 },
    { label: '参与评分', value: data.scored, icon: GitBranch, color: T.teal },
    { label: '精选输出', value: data.stages.find((s) => s.key === 'selected')?.count || 0, icon: CheckCircle2, color: T.primary },
    { label: '观察窗口', value: data.hours === 168 ? '7天' : `${data.hours}h`, icon: ShieldAlert, color: T.amber },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Panel key={card.label} style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: T.gray500 }}>{card.label}</div>
              <Icon size={15} color={card.color} />
            </div>
            <MetricValue value={card.value} color={card.color} />
          </Panel>
        );
      })}
    </div>
  );
}

export function Funnel({ data, selectedKey }: { data: ScoringFlowResponse; selectedKey?: string }) {
  const max = Math.max(...data.stages.map((s) => s.count), 1);
  return (
    <Panel style={{ padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Filter size={16} color={T.primary} />
        <div style={{ fontSize: 14, fontWeight: 700, color: T.gray800 }}>评分漏斗</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(112px, 1fr))', gap: 10, overflowX: 'auto' }}>
        {data.stages.map((stage) => {
          const palette = STAGE_COLORS[stage.key] || STAGE_COLORS.candidates;
          const width = 52 + (stage.count / max) * 48;
          const active = selectedKey === stage.key;
          return (
            <div
              key={stage.key}
              style={{
                minWidth: 112,
                border: `1px solid ${active ? palette.color : palette.border}`,
                background: palette.bg,
                borderRadius: T.radiusSm,
                padding: '14px 12px',
                boxShadow: active ? `0 0 0 2px ${palette.color}22` : 'none',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700, color: palette.color, marginBottom: 10 }}>{stage.label}</div>
              <div style={{ height: 42, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: `${width}%`, height: 34, borderRadius: 6, background: palette.color, opacity: 0.9 }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 10 }}>
                <span style={{ fontSize: 22, fontWeight: 800, color: T.gray900, fontFamily: T.mono }}>{stage.count}</span>
                <span style={{ fontSize: 11, color: T.gray500 }}>{pct(stage.retention)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function MixList({ title, items, color }: { title: string; items: Array<{ label: string; count: number }>; color: string }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <Panel style={{ padding: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: T.gray800, marginBottom: 12 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {items.length === 0 ? (
          <div style={{ fontSize: 12, color: T.gray400 }}>暂无样本</div>
        ) : items.map((item) => (
          <div key={item.label} style={{ display: 'grid', gridTemplateColumns: '78px 1fr 34px', alignItems: 'center', gap: 8 }}>
            <div title={item.label} style={{ fontSize: 12, color: T.gray600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.label}
            </div>
            <div style={{ height: 8, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ width: `${Math.max(4, (item.count / max) * 100)}%`, height: '100%', background: color }} />
            </div>
            <div style={{ fontSize: 11, fontFamily: T.mono, color: T.gray500, textAlign: 'right' }}>{item.count}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function SampleList({
  samples,
  selectedId,
  onSelect,
}: {
  samples: ScoringFlowSample[];
  selectedId?: number;
  onSelect: (sample: ScoringFlowSample) => void;
}) {
  return (
    <Panel style={{ minHeight: 520, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${T.gray100}`, display: 'flex', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: T.gray800 }}>候选样本池</div>
        <div style={{ fontSize: 11, color: T.gray400 }}>按最终分排序</div>
      </div>
      <div style={{ maxHeight: 628, overflowY: 'auto' }}>
        {samples.map((sample) => {
          const active = sample.id === selectedId;
          return (
            <button
              key={sample.id}
              onClick={() => onSelect(sample)}
              style={{
                width: '100%',
                border: 'none',
                borderBottom: `1px solid ${T.gray100}`,
                background: active ? T.primaryLight : T.white,
                padding: '13px 16px',
                textAlign: 'left',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: 42,
                    flexShrink: 0,
                    textAlign: 'right',
                    fontSize: 18,
                    fontWeight: 800,
                    color: sample.selected ? T.primary : T.gray500,
                    fontFamily: T.mono,
                  }}
                >
                  {Math.round(sample.final_score)}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.gray800, lineHeight: 1.45 }}>{sample.title}</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 7, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, borderRadius: 4, padding: '2px 6px' }}>
                      {sample.category}
                    </span>
                    <span style={{ fontSize: 10, color: T.gray500 }}>{sample.source_name || '未知来源'}</span>
                    {sample.selected && (
                      <span style={{ fontSize: 10, color: T.primary, background: T.primaryLight, borderRadius: 4, padding: '2px 6px', fontWeight: 700 }}>
                        SELECTED
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

export function PathPanel({
  sample,
  onFeedback,
  feedbacking,
}: {
  sample?: ScoringFlowSample;
  onFeedback: (sample: ScoringFlowSample, type: FeedbackType) => void;
  feedbacking: boolean;
}) {
  const dims = sample?.dimension_scores || {};
  const dimRows = [
    ['信息密度', Number(dims.info_density || 0)],
    ['可操作性', Number(dims.actionability || 0)],
    ['创作者价值', Number(dims.creator_value || 0)],
    ['爆文潜力', Number(dims.viral_potential || 0)],
    ['来源权威', Number(dims.source_authority || 0)],
    ['新鲜度', Number(dims.freshness || 0)],
  ] as const;

  return (
    <Panel style={{ minHeight: 520, padding: 18 }}>
      {!sample ? (
        <div style={{ color: T.gray400, fontSize: 13 }}>选择一个候选样本查看路径</div>
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: sample.selected ? T.primary : T.gray500, marginBottom: 8 }}>
                {sample.selected ? '进入精选输出' : '未进入精选'}
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: T.gray900, lineHeight: 1.35 }}>{sample.title}</div>
            </div>
            {sample.url && (
              <a href={sample.url} target="_blank" rel="noreferrer" title="打开原文" style={{ color: T.gray400, paddingTop: 2 }}>
                <ExternalLink size={16} />
              </a>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 18 }}>
            {[
              ['基础分', sample.base_score, T.gray800],
              ['最终分', sample.final_score, T.primary],
              ['门槛', sample.threshold_used, T.amber],
            ].map(([label, value, color]) => (
              <div key={label as string} style={{ border: `1px solid ${T.gray100}`, borderRadius: T.radiusSm, padding: 10 }}>
                <div style={{ fontSize: 10, color: T.gray400, marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 21, fontWeight: 800, fontFamily: T.mono, color: color as string }}>{fmt(value as number)}</div>
              </div>
            ))}
          </div>

          <div style={{ border: `1px solid ${T.gray100}`, borderRadius: T.radiusSm, padding: 12, marginBottom: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.gray800 }}>人工反馈</div>
              <div style={{ fontSize: 12, fontFamily: T.mono, color: sample.feedback_score >= 0 ? T.teal : T.red }}>
                {sample.feedback_score > 0 ? '+' : ''}{fmt(sample.feedback_score)}
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <FeedbackButton
                icon={<Plus size={13} />}
                label="正向加分"
                disabled={feedbacking}
                onClick={() => onFeedback(sample, 'great_pick')}
                palette={{ color: T.teal, bg: T.tealLight, border: T.tealBorder }}
              />
              <FeedbackButton
                icon={<Minus size={13} />}
                label="负向扣分"
                disabled={feedbacking}
                onClick={() => onFeedback(sample, 'not_relevant')}
                palette={{ color: T.red, bg: T.redLight, border: `${T.red}33` }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
            <FactorBar label="质量因子" value={sample.quality_factor} color={T.teal} />
            <FactorBar label="风险因子" value={sample.risk_factor} color={T.amber} />
            <FactorBar label="时效衰减" value={sample.time_decay} color="#3B82F6" />
            <FactorBar label="多样性因子" value={sample.diversity_factor} color={T.purple} />
          </div>

          <div style={{ borderTop: `1px solid ${T.gray100}`, paddingTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.gray800, marginBottom: 12 }}>特征评分路径</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {dimRows.map(([label, value]) => (
                <ProgressRow key={label} label={label} value={value} color={T.primary} />
              ))}
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}
