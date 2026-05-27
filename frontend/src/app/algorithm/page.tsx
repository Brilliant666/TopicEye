'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
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
import { T } from '@/lib/design-tokens';
import { contentsApi, feedbackApi, type FeedbackType, type ScoringFlowResponse, type ScoringFlowSample } from '@/lib/api';

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

function Funnel({ data, selectedKey }: { data: ScoringFlowResponse; selectedKey?: string }) {
  const max = Math.max(...data.stages.map((s) => s.count), 1);
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Filter size={16} color={T.primary} />
        <div style={{ fontSize: 14, fontWeight: 700, color: T.gray800 }}>评分漏斗</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(112px, 1fr))', gap: 10, overflowX: 'auto' }}>
        {data.stages.map((stage, index) => {
          const palette = STAGE_COLORS[stage.key] || STAGE_COLORS.candidates;
          const width = 52 + (stage.count / max) * 48;
          const active = selectedKey === stage.key;
          return (
            <React.Fragment key={stage.key}>
              <div
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
                  <div
                    style={{
                      width: `${width}%`,
                      height: 34,
                      borderRadius: 6,
                      background: palette.color,
                      opacity: 0.9,
                    }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 10 }}>
                  <span style={{ fontSize: 22, fontWeight: 800, color: T.gray900, fontFamily: T.mono }}>{stage.count}</span>
                  <span style={{ fontSize: 11, color: T.gray500 }}>{pct(stage.retention)}</span>
                </div>
              </div>
              {index < data.stages.length - 1 ? null : null}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

function MixList({ title, items, color }: { title: string; items: Array<{ label: string; count: number }>; color: string }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, padding: 16 }}>
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
    </div>
  );
}

function SampleList({
  samples,
  selectedId,
  onSelect,
}: {
  samples: ScoringFlowSample[];
  selectedId?: number;
  onSelect: (sample: ScoringFlowSample) => void;
}) {
  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, minHeight: 520, overflow: 'hidden' }}>
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
    </div>
  );
}

function PathPanel({
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
    ['信息密度', dims.info_density],
    ['可操作性', dims.actionability],
    ['创作者价值', dims.creator_value],
    ['爆文潜力', dims.viral_potential],
    ['来源权威', dims.source_authority],
    ['新鲜度', dims.freshness],
  ];

  return (
    <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, minHeight: 520, padding: 18 }}>
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
              <button
                onClick={() => onFeedback(sample, 'great_pick')}
                disabled={feedbacking}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  padding: '9px 10px',
                  border: `1px solid ${T.tealBorder}`,
                  background: T.tealLight,
                  color: T.teal,
                  borderRadius: T.radiusSm,
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: feedbacking ? 'wait' : 'pointer',
                }}
              >
                <Plus size={13} /> 正向加分
              </button>
              <button
                onClick={() => onFeedback(sample, 'not_relevant')}
                disabled={feedbacking}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  padding: '9px 10px',
                  border: `1px solid ${T.red}33`,
                  background: T.redLight,
                  color: T.red,
                  borderRadius: T.radiusSm,
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: feedbacking ? 'wait' : 'pointer',
                }}
              >
                <Minus size={13} /> 负向扣分
              </button>
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
                <div key={label as string} style={{ display: 'grid', gridTemplateColumns: '76px 1fr 46px', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontSize: 12, color: T.gray500 }}>{label}</div>
                  <div style={{ height: 8, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ width: `${Math.max(3, Math.min(100, Number(value || 0)))}%`, height: '100%', background: T.primary }} />
                  </div>
                  <div style={{ fontSize: 11, color: T.gray600, fontFamily: T.mono, textAlign: 'right' }}>{fmt(Number(value || 0))}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function AlgorithmPage() {
  const [hours, setHours] = useState(48);
  const [data, setData] = useState<ScoringFlowResponse | null>(null);
  const [selected, setSelected] = useState<ScoringFlowSample | undefined>();
  const [loading, setLoading] = useState(true);
  const [feedbacking, setFeedbacking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFlow = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await contentsApi.scoringFlow({ hours, limit: 160 });
      setData(result);
      setSelected((prev) => result.samples.find((s) => s.id === prev?.id) || result.samples[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '算法流程加载失败');
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => { void fetchFlow(); }, [fetchFlow]);

  const handleFeedback = useCallback(async (sample: ScoringFlowSample, type: FeedbackType) => {
    setFeedbacking(true);
    setError(null);
    try {
      await feedbackApi.submit(sample.id, type, 'algorithm-flow');
      await fetchFlow();
    } catch (err) {
      const message = err instanceof Error ? err.message : '反馈提交失败';
      if (message.includes('already exists') || message.includes('409')) {
        setError('这条内容已经提交过同类型反馈。');
      } else {
        setError(message);
      }
    } finally {
      setFeedbacking(false);
    }
  }, [fetchFlow]);

  const selectedKey = useMemo(() => {
    if (!selected) return undefined;
    if (selected.selected) return 'selected';
    if (selected.quality_factor <= 0.55) return 'quality';
    if (selected.risk_factor <= 0.55) return 'risk';
    if (selected.time_decay < 0.6) return 'freshness';
    if (selected.diversity_factor < 0.85) return 'diversity';
    return 'candidates';
  }, [selected]);

  return (
    <div className="fade-in" style={{ padding: '28px 32px', height: '100%', overflowY: 'auto', background: T.bg }}>
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
              onClick={() => setHours(h)}
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
            onClick={() => void fetchFlow()}
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

      {error && (
        <div style={{ background: T.redLight, color: T.red, border: `1px solid ${T.red}22`, borderRadius: T.radiusSm, padding: 14, marginBottom: 18, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading && !data ? (
        <div style={{ color: T.gray400, fontSize: 13 }}>加载算法流程...</div>
      ) : data ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
            {[
              { label: '数据库候选', value: data.total, icon: SlidersHorizontal, color: T.gray800 },
              { label: '参与评分', value: data.scored, icon: GitBranch, color: T.teal },
              { label: '精选输出', value: data.stages.find((s) => s.key === 'selected')?.count || 0, icon: CheckCircle2, color: T.primary },
              { label: '观察窗口', value: data.hours === 168 ? '7天' : `${data.hours}h`, icon: ShieldAlert, color: T.amber },
            ].map((card) => {
              const Icon = card.icon;
              return (
                <div key={card.label} style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div style={{ fontSize: 12, color: T.gray500 }}>{card.label}</div>
                    <Icon size={15} color={card.color} />
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 800, fontFamily: T.mono, color: card.color }}>{card.value}</div>
                </div>
              );
            })}
          </div>

          <div style={{ marginBottom: 14 }}>
            <Funnel data={data} selectedKey={selectedKey} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 0.95fr) minmax(420px, 1.25fr) minmax(340px, 0.95fr)', gap: 14, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <MixList title="类别混排压力" items={data.category_mix} color={T.purple} />
              <MixList title="来源混排压力" items={data.source_mix} color={T.teal} />
            </div>
            <SampleList samples={data.samples} selectedId={selected?.id} onSelect={setSelected} />
            <PathPanel sample={selected} onFeedback={handleFeedback} feedbacking={feedbacking} />
          </div>
        </>
      ) : null}
    </div>
  );
}
