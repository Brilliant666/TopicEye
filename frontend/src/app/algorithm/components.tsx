'use client';

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
import { Badge, Button, Metric, Panel, Toolbar } from '@/components/ui';
import type { FeedbackType, ScoringFlowResponse, ScoringFlowSample } from '@/lib/api';

const COLORS = {
  primary: '#FF6B35',
  primaryLight: '#FFF4EE',
  primaryBorder: '#FFD0B5',
  teal: '#00C9A7',
  tealLight: '#E6FAF5',
  tealBorder: '#A7F0DB',
  purple: '#8B5CF6',
  purpleLight: '#F0EBFF',
  purpleBorder: '#C4B5FD',
  amber: '#D97706',
  amberLight: '#FEF3C7',
  amberBorder: '#FCD34D',
  red: '#EF4444',
  gray50: '#FAFAFA',
  gray200: '#E5E7EB',
  gray500: '#6B7280',
  gray700: '#374151',
  gray800: '#1F2937',
};

const STAGE_COLORS: Record<string, { color: string; bg: string; border: string; soft: string }> = {
  candidates: { color: COLORS.gray700, bg: COLORS.gray50, border: COLORS.gray200, soft: '#F8FAFC' },
  quality: { color: COLORS.teal, bg: COLORS.tealLight, border: COLORS.tealBorder, soft: '#F2FFFC' },
  risk: { color: COLORS.amber, bg: COLORS.amberLight, border: COLORS.amberBorder, soft: '#FFFBEB' },
  freshness: { color: '#3B82F6', bg: '#EFF6FF', border: '#BFDBFE', soft: '#F8FBFF' },
  diversity: { color: COLORS.purple, bg: COLORS.purpleLight, border: COLORS.purpleBorder, soft: '#FBF8FF' },
  selected: { color: COLORS.primary, bg: COLORS.primaryLight, border: COLORS.primaryBorder, soft: '#FFF9F6' },
};

const MIX_TONES = {
  purple: { color: COLORS.purple, bg: COLORS.purpleLight, border: COLORS.purpleBorder },
  teal: { color: COLORS.teal, bg: COLORS.tealLight, border: COLORS.tealBorder },
} as const;

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
      <div className="mb-1.5 flex justify-between text-[11px] text-gray-500">
        <span>{label}</span>
        <span className="font-mono">{fmt(value, 2)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-gray-100">
        <div className="h-full rounded-full" style={{ width: `${width}%`, background: color }} />
      </div>
    </div>
  );
}

function ProgressRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="grid grid-cols-[78px_minmax(0,1fr)_46px] items-center gap-2">
      <div className="truncate text-xs text-gray-500">{label}</div>
      <div className="h-2 overflow-hidden rounded-full bg-gray-100">
        <div className="h-full rounded-full" style={{ width: `${Math.max(3, Math.min(100, value))}%`, background: color }} />
      </div>
      <div className="text-right font-mono text-[11px] text-gray-600">{fmt(value)}</div>
    </div>
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
    <header className="relative mb-5 overflow-hidden rounded-lg border border-gray-200 bg-white px-5 py-5 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary to-teal" />
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone="primary" className="gap-1.5 font-mono">
              <GitBranch size={13} strokeWidth={2.4} />
              SCORING FLOW
            </Badge>
            <span className="text-xs font-bold text-gray-500">最近 {hours === 168 ? '7 天' : `${hours} 小时`}</span>
          </div>
          <h1 className="m-0 text-[28px] font-black leading-tight text-gray-900">算法流程</h1>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-gray-500">
            从候选样本进入评分漏斗，沿质量、风险、时效和多样性路径扣分或加权，最终形成精选输出；人工反馈会回写到样本的路径分。
          </p>
        </div>

        <Toolbar className="lg:justify-end">
          <div className="inline-flex rounded-sm border border-gray-200 bg-gray-100 p-1">
            {[24, 48, 168].map((h) => {
              const active = hours === h;
              return (
                <button
                  key={h}
                  onClick={() => onHoursChange(h)}
                  className={`min-h-8 rounded-xs px-3 text-xs font-black transition ${
                    active ? 'bg-white text-primary shadow-[0_1px_3px_rgba(15,23,42,0.08)]' : 'text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {h === 168 ? '7天' : `${h}h`}
                </button>
              );
            })}
          </div>
          <Button
            onClick={onRefresh}
            disabled={loading}
            title="刷新"
            variant="secondary"
            className="h-9 w-9 px-0 py-0"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </Button>
        </Toolbar>
      </div>
    </header>
  );
}

export function SummaryGrid({ data }: { data: ScoringFlowResponse }) {
  const cards: Array<{ label: string; value: number | string; icon: LucideIcon; colorClass: string; iconClass: string }> = [
    { label: '数据库候选', value: data.total, icon: SlidersHorizontal, colorClass: 'text-gray-800', iconClass: 'text-gray-800' },
    { label: '参与评分', value: data.scored, icon: GitBranch, colorClass: 'text-teal', iconClass: 'text-teal' },
    { label: '精选输出', value: data.stages.find((s) => s.key === 'selected')?.count || 0, icon: CheckCircle2, colorClass: 'text-primary', iconClass: 'text-primary' },
    { label: '观察窗口', value: data.hours === 168 ? '7天' : `${data.hours}h`, icon: ShieldAlert, colorClass: 'text-amber', iconClass: 'text-amber' },
  ];

  return (
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Metric
            key={card.label}
            label={card.label}
            value={card.value}
            colorClass={card.colorClass}
            icon={<Icon size={15} className={card.iconClass} />}
          />
        );
      })}
    </div>
  );
}

export function Funnel({ data, selectedKey }: { data: ScoringFlowResponse; selectedKey?: string }) {
  const max = Math.max(...data.stages.map((s) => s.count), 1);
  const clampWidth = (count: number) => {
    if (count <= 0) return 8;
    return Math.max(14, Math.min(100, (count / max) * 100));
  };

  return (
    <Panel className="overflow-hidden p-4 lg:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Filter size={16} color={COLORS.primary} />
          <div className="text-sm font-black text-gray-800">评分漏斗</div>
        </div>
        <div className="text-xs text-gray-400">宽度按样本留存比例缩放</div>
      </div>

      <div className="mx-auto flex max-w-[880px] flex-col gap-2.5">
        {data.stages.map((stage, index) => {
          const palette = STAGE_COLORS[stage.key] || STAGE_COLORS.candidates;
          const width = clampWidth(stage.count);
          const active = selectedKey === stage.key;
          const previous = data.stages[index - 1];
          const lost = previous ? Math.max(0, previous.count - stage.count) : 0;
          const stageShare = stage.count / max;
          return (
            <div
              key={stage.key}
              className="grid grid-cols-[92px_minmax(0,1fr)_86px] items-center gap-3"
            >
              <div className="min-w-0 text-right">
                <div className="truncate text-xs font-black" style={{ color: palette.color }}>{stage.label}</div>
                <div className="mt-1 font-mono text-[11px] text-gray-400">{pct(stageShare)}</div>
              </div>

              <div className="relative h-[58px] min-w-0">
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-gray-100" />
                <div
                  className="absolute left-1/2 top-0 flex h-full -translate-x-1/2 items-center justify-between gap-3 overflow-hidden rounded-sm border px-4 transition"
                  style={{
                    width: `${width}%`,
                    minWidth: stage.count > 0 ? 112 : 60,
                    maxWidth: '100%',
                    borderColor: active ? palette.color : palette.border,
                    background: `linear-gradient(135deg, ${palette.bg}, ${palette.soft})`,
                    boxShadow: active ? `0 0 0 2px ${palette.color}22, 0 14px 26px rgba(15,23,42,0.08)` : '0 8px 18px rgba(15,23,42,0.04)',
                    clipPath: 'polygon(3% 0, 97% 0, 100% 100%, 0 100%)',
                  }}
                >
                  <span className="truncate text-[13px] font-black text-gray-800">{stage.label}</span>
                  <span className="shrink-0 font-mono text-xl font-black leading-none" style={{ color: palette.color }}>
                    {stage.count}
                  </span>
                </div>
              </div>

              <div className="min-w-0">
                {previous ? (
                  <>
                    <div className="font-mono text-xs font-black text-gray-700">-{lost}</div>
                    <div className="mt-1 text-[10px] text-gray-400">流失</div>
                  </>
                ) : (
                  <>
                    <div className="font-mono text-xs font-black text-gray-700">{stage.count}</div>
                    <div className="mt-1 text-[10px] text-gray-400">入口</div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function MixList({ title, items, tone }: { title: string; items: Array<{ label: string; count: number }>; tone: keyof typeof MIX_TONES }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  const palette = MIX_TONES[tone];
  return (
    <Panel className="p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-black text-gray-800">{title}</div>
        <Badge tone={tone} className="font-mono text-[10px]">
          {items.length}
        </Badge>
      </div>
      <div className="flex flex-col gap-2.5">
        {items.length === 0 ? (
          <div className="text-xs text-gray-400">暂无样本</div>
        ) : items.map((item) => (
          <div key={item.label} className="grid grid-cols-[78px_minmax(0,1fr)_34px] items-center gap-2">
            <div title={item.label} className="truncate text-xs text-gray-600">
              {item.label}
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div className="h-full rounded-full" style={{ width: `${Math.max(4, (item.count / max) * 100)}%`, background: palette.color }} />
            </div>
            <div className="text-right font-mono text-[11px] text-gray-500">{item.count}</div>
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
    <Panel className="min-h-[520px] overflow-hidden">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3.5">
        <div>
          <div className="text-sm font-black text-gray-800">候选样本池</div>
          <div className="mt-0.5 text-[11px] text-gray-400">点击样本查看评分路径</div>
        </div>
        <div className="font-mono text-[11px] text-gray-400">FINAL SCORE</div>
      </div>
      <div className="max-h-[628px] overflow-y-auto">
        {samples.map((sample) => {
          const active = sample.id === selectedId;
          return (
            <button
              key={sample.id}
              onClick={() => onSelect(sample)}
              className={`w-full border-0 border-b border-gray-100 px-4 py-3.5 text-left transition ${
                active ? 'bg-primary-light' : 'bg-white hover:bg-gray-50'
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className="w-11 shrink-0 text-right font-mono text-lg font-black leading-tight"
                  style={{ color: sample.selected ? COLORS.primary : active ? COLORS.gray800 : COLORS.gray500 }}
                >
                  {Math.round(sample.final_score)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-[13px] font-bold leading-5 text-gray-800">{sample.title}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <Badge tone="neutral" className="rounded-xs px-1.5 py-0.5 text-[10px] font-bold">
                      {sample.category}
                    </Badge>
                    <span className="max-w-[150px] truncate text-[10px] text-gray-500">{sample.source_name || '未知来源'}</span>
                    {sample.selected && (
                      <Badge tone="primary" className="rounded-xs bg-white px-1.5 py-0.5 text-[10px]">
                        SELECTED
                      </Badge>
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
    <Panel className="min-h-[520px] p-4 lg:p-5">
      {!sample ? (
        <div className="flex min-h-[460px] items-center justify-center rounded-sm border border-dashed border-gray-200 bg-gray-50 px-6 text-center text-sm text-gray-400">
          选择一个候选样本查看路径
        </div>
      ) : (
        <>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Badge tone={sample.selected ? 'primary' : 'neutral'} className="mb-2">
                {sample.selected ? '进入精选输出' : '未进入精选'}
              </Badge>
              <div className="text-lg font-black leading-snug text-gray-900">{sample.title}</div>
            </div>
            {sample.url && (
              <a
                href={sample.url}
                target="_blank"
                rel="noreferrer"
                title="打开原文"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-gray-200 text-gray-400 transition hover:border-primary-border hover:text-primary"
              >
                <ExternalLink size={16} />
              </a>
            )}
          </div>

          <div className="mb-4 grid grid-cols-3 gap-2.5">
            {[
              ['基础分', sample.base_score, COLORS.gray800],
              ['最终分', sample.final_score, COLORS.primary],
              ['门槛', sample.threshold_used, COLORS.amber],
            ].map(([label, value, color]) => (
              <div key={label as string} className="min-w-0 rounded-sm border border-gray-100 bg-gray-50 p-2.5">
                <div className="mb-1 text-[10px] text-gray-400">{label}</div>
                <div className="font-mono text-xl font-black leading-none" style={{ color: color as string }}>{fmt(value as number)}</div>
              </div>
            ))}
          </div>

          <div className="mb-4 rounded-sm border border-gray-100 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div className="text-xs font-black text-gray-800">人工反馈</div>
              <div className="font-mono text-xs" style={{ color: sample.feedback_score >= 0 ? COLORS.teal : COLORS.red }}>
                {sample.feedback_score > 0 ? '+' : ''}{fmt(sample.feedback_score)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="success"
                disabled={feedbacking}
                onClick={() => onFeedback(sample, 'great_pick')}
              >
                <Plus size={13} />
                正向加分
              </Button>
              <Button
                variant="danger"
                disabled={feedbacking}
                onClick={() => onFeedback(sample, 'not_relevant')}
              >
                <Minus size={13} />
                负向扣分
              </Button>
            </div>
          </div>

          <div className="mb-5 flex flex-col gap-3 rounded-sm border border-gray-100 bg-gray-50 p-3">
            <div className="text-xs font-black text-gray-800">路径因子</div>
            <FactorBar label="质量因子" value={sample.quality_factor} color={COLORS.teal} />
            <FactorBar label="风险因子" value={sample.risk_factor} color={COLORS.amber} />
            <FactorBar label="时效衰减" value={sample.time_decay} color="#3B82F6" />
            <FactorBar label="多样性因子" value={sample.diversity_factor} color={COLORS.purple} />
          </div>

          <div className="border-t border-gray-100 pt-4">
            <div className="mb-3 text-sm font-black text-gray-800">特征评分路径</div>
            <div className="flex flex-col gap-2.5">
              {dimRows.map(([label, value]) => (
                <ProgressRow key={label} label={label} value={value} color={COLORS.primary} />
              ))}
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}
