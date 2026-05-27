'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowRight,
  BarChart3,
  Beaker,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Coins,
  FlaskConical,
  Gauge,
  History,
  KeyRound,
  Layers3,
  Play,
  Plus,
  Power,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  Trash2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import { modelsApi } from '@/lib/api';
import type { LlmModelItem, EvalRun, EvalResult, ModelUsageSummary } from '@/lib/api';

type Tab = 'models' | 'evaluate' | 'usage' | 'history';

type ProviderPreset = {
  label: string;
  baseUrl: string;
  modelPlaceholder: string;
  costPer1MInput?: number;
  costPer1MInputCacheHit?: number;
  costPer1MOutput?: number;
  pricingNote?: string;
};

const PROVIDER_PRESETS: Record<string, ProviderPreset> = {
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    modelPlaceholder: 'gpt-4.1-mini',
  },
  deepseek: {
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    modelPlaceholder: 'deepseek-chat',
    costPer1MInput: 1,
    costPer1MInputCacheHit: 0.02,
    costPer1MOutput: 2,
    pricingNote: 'DeepSeek 按百万 tokens 计费；V4 Flash 默认 ¥1/¥0.02/¥2，V4 Pro 当前优惠价 ¥3/¥0.025/¥6',
  },
  minimax: {
    label: 'MiniMax',
    baseUrl: 'https://api.minimaxi.com/v1',
    modelPlaceholder: 'MiniMax-Text-01',
  },
  zhipu: {
    label: '智谱 GLM',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4/',
    modelPlaceholder: 'glm-4-plus',
  },
  custom: {
    label: '自定义 OpenAI 兼容',
    baseUrl: '',
    modelPlaceholder: 'provider/model-name',
  },
};

function deepSeekPricingForModel(modelId: string) {
  const normalized = modelId.toLowerCase();
  if (normalized.includes('v4-pro')) {
    return { input: 3, cacheHit: 0.025, output: 6 };
  }
  return { input: 1, cacheHit: 0.02, output: 2 };
}

function pricingForProviderModel(provider: string, modelId: string) {
  if (provider === 'deepseek') return deepSeekPricingForModel(modelId);
  const preset = PROVIDER_PRESETS[provider];
  if (!preset?.costPer1MInput && !preset?.costPer1MOutput && !preset?.costPer1MInputCacheHit) return null;
  return {
    input: preset.costPer1MInput,
    cacheHit: preset.costPer1MInputCacheHit,
    output: preset.costPer1MOutput,
  };
}

const promptTypeLabel: Record<string, string> = {
  analysis: '选题分析',
  daily_report: 'AI 日报',
  weekly_digest: 'AI 周刊',
  classification: '内容分类',
  custom: '自定义',
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value || 0);
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `${(value / 1000).toFixed(1)}K`;
  return formatNumber(value);
}

function formatCurrency(value: number): string {
  return `¥${(value || 0).toFixed(value >= 10 ? 2 : 4)}`;
}

function formatPerMillion(value: number | null | undefined): string {
  return value !== null && value !== undefined ? `${formatCurrency(value)} / 百万` : '未配置';
}

function parseOptionalNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function Surface({
  title,
  icon: Icon,
  hint,
  children,
  style,
}: {
  title: string;
  icon: LucideIcon;
  hint?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section style={{
      background: T.white,
      border: `1px solid ${T.gray200}`,
      borderRadius: T.radius,
      padding: '18px 20px',
      ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Icon size={16} color={T.primary} strokeWidth={2.2} />
          <span style={{ fontSize: 14, fontWeight: 800, color: T.gray900 }}>{title}</span>
        </div>
        {hint && <span style={{ fontSize: 11, color: T.gray400, whiteSpace: 'nowrap' }}>{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  hint,
  color,
  tone = 'neutral',
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint: string;
  color: string;
  tone?: 'primary' | 'teal' | 'amber' | 'neutral';
}) {
  const toneStyle = {
    primary: { bg: T.primaryLight, border: T.primaryBorder },
    teal: { bg: T.tealLight, border: T.tealBorder },
    amber: { bg: T.amberLight, border: T.amberBorder },
    neutral: { bg: T.gray50, border: T.gray200 },
  }[tone];

  return (
    <div style={{
      background: toneStyle.bg,
      border: `1px solid ${toneStyle.border}`,
      borderRadius: T.radiusSm,
      padding: '13px 14px',
      minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}>
        <Icon size={14} color={color} strokeWidth={2.2} />
        <span style={{ fontSize: 11, fontWeight: 800, color: T.gray500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 25, lineHeight: 1, fontWeight: 900, color, fontFamily: T.mono }}>
        {value}
      </div>
      <div style={{ marginTop: 5, fontSize: 10.5, color: T.gray400 }}>{hint}</div>
    </div>
  );
}

function StatusPill({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'primary' | 'teal' | 'amber' | 'red' | 'neutral';
}) {
  const styleMap = {
    primary: { bg: T.primaryLight, border: T.primaryBorder, color: T.primary },
    teal: { bg: T.tealLight, border: T.tealBorder, color: T.teal },
    amber: { bg: T.amberLight, border: T.amberBorder, color: T.amber },
    red: { bg: T.redLight, border: '#FCA5A5', color: T.red },
    neutral: { bg: T.gray50, border: T.gray200, color: T.gray500 },
  }[tone];

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      padding: '3px 8px',
      borderRadius: 999,
      background: styleMap.bg,
      border: `1px solid ${styleMap.border}`,
      color: styleMap.color,
      fontSize: 11,
      fontWeight: 800,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

export default function ModelEvalPage() {
  const [tab, setTab] = useState<Tab>('models');
  const [models, setModels] = useState<LlmModelItem[]>([]);
  const [usage, setUsage] = useState<ModelUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);

  const fetchModels = useCallback(async () => {
    try {
      const res = await modelsApi.list();
      setModels(res.models);
    } catch (e) { console.error('fetchModels', e); }
    setLoading(false);
  }, []);

  const fetchUsage = useCallback(async () => {
    try {
      setUsageLoading(true);
      const res = await modelsApi.usageSummary(30);
      setUsage(res);
    } catch (e) { console.error('fetchUsage', e); }
    setUsageLoading(false);
  }, []);

  const refreshAll = useCallback(() => {
    fetchModels();
    fetchUsage();
  }, [fetchModels, fetchUsage]);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  const enabledCount = models.filter(m => m.enabled).length;
  const runnableCount = models.filter(m => m.enabled && (m.api_key_set || !m.api_base)).length;
  const primaryModel = models.find(m => m.is_primary);
  const fallbackModel = models.find(m => m.is_fallback);

  return (
    <div style={{ padding: '28px 40px 64px', maxWidth: 1480, margin: '0 auto' }}>
      <section style={{
        position: 'relative',
        overflow: 'hidden',
        background: T.white,
        border: `1px solid ${T.gray200}`,
        borderRadius: T.radius,
        padding: '22px 24px',
        marginBottom: 18,
        boxShadow: '0 14px 36px rgba(15, 23, 42, 0.06)',
      }}>
        <div style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          height: 4,
          background: `linear-gradient(90deg, ${T.primary}, ${T.teal})`,
        }} />
        <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 20, alignItems: 'start' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', marginBottom: 12 }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 11,
                fontWeight: 900,
                color: T.primary,
                background: T.primaryLight,
                border: `1px solid ${T.primaryBorder}`,
                borderRadius: 999,
                padding: '4px 10px',
                fontFamily: T.mono,
              }}>
                <BrainCircuit size={13} strokeWidth={2.4} />
                AI ENGINE
              </span>
              <span style={{ fontSize: 12, fontWeight: 700, color: T.gray500 }}>模型配置与测评</span>
            </div>
            <h1 style={{ fontSize: 28, lineHeight: 1.12, fontWeight: 900, color: T.gray900, margin: 0 }}>
              AI 引擎工作台
            </h1>
            <p style={{ fontSize: 13, lineHeight: 1.7, color: T.gray500, margin: '8px 0 0', maxWidth: 760 }}>
              管理内容分析、日报、周刊和分类任务使用的模型，定期做 A/B 测评，保留人工评分作为模型选择依据。
            </p>
          </div>
          <button
            onClick={refreshAll}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 7,
              padding: '9px 15px',
              fontSize: 13,
              fontWeight: 800,
              background: T.white,
              color: T.gray600,
              border: `1px solid ${T.gray200}`,
              borderRadius: T.radiusSm,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            <RefreshCw size={14} strokeWidth={2.2} />
            刷新数据
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(170px, 100%), 1fr))', gap: 10, marginTop: 18 }}>
          <StatTile icon={Layers3} label="模型配置" value={models.length} hint={`${enabledCount} 个启用`} color={T.primary} tone="primary" />
          <StatTile icon={KeyRound} label="可测模型" value={runnableCount} hint="具备调用条件" color={T.teal} tone="teal" />
          <StatTile icon={ShieldCheck} label="主模型" value={primaryModel ? 1 : 0} hint={primaryModel?.name || '未设置'} color={T.amber} tone="amber" />
          <StatTile icon={Clock3} label="备用模型" value={fallbackModel ? 1 : 0} hint={fallbackModel?.name || '未设置'} color={T.gray700} />
          <StatTile icon={Gauge} label="30日 Token" value={usage ? formatTokens(usage.total.tokens_total) : '-'} hint={`输入 ${formatTokens(usage?.total.tokens_input || 0)} · 输出 ${formatTokens(usage?.total.tokens_output || 0)}`} color={T.purple} />
          <StatTile icon={Coins} label="费用预估" value={usage ? formatCurrency(usage.total.estimated_cost) : '-'} hint={`${usage?.total.calls || 0} 次测评调用`} color={T.primary} tone="primary" />
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(170px, 100%), 1fr))', gap: 10, marginBottom: 18 }}>
        {[
          { key: 'models' as const, label: '模型配置', desc: '主备模型、密钥和限流参数', icon: Settings2 },
          { key: 'evaluate' as const, label: 'A/B 测评', desc: '多模型同题测试并人工评分', icon: FlaskConical },
          { key: 'usage' as const, label: '用量统计', desc: 'Token 消耗和费用预估', icon: BarChart3 },
          { key: 'history' as const, label: '测评历史', desc: '查看历史运行与评分记录', icon: History },
        ].map(item => {
          const Icon = item.icon;
          const active = tab === item.key;
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              style={{
                textAlign: 'left',
                padding: '13px 14px',
                borderRadius: T.radius,
                border: `1px solid ${active ? T.primaryBorder : T.gray200}`,
                background: active ? T.primaryLight : T.white,
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                <Icon size={15} color={active ? T.primary : T.gray500} strokeWidth={2.2} />
                <span style={{ fontSize: 13, fontWeight: 850, color: active ? T.primary : T.gray800 }}>{item.label}</span>
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.45, color: T.gray500 }}>{item.desc}</div>
            </button>
          );
        })}
      </div>

      {loading ? (
        <Surface title="加载状态" icon={Beaker}>
          <div style={{ textAlign: 'center', color: T.gray400, padding: 48 }}>加载中...</div>
        </Surface>
      ) : (
        <>
          {tab === 'models' && <ModelsTab models={models} onRefresh={refreshAll} />}
          {tab === 'evaluate' && <EvaluateTab models={models} />}
          {tab === 'usage' && <UsageTab usage={usage} loading={usageLoading} onRefresh={fetchUsage} />}
          {tab === 'history' && <HistoryTab />}
        </>
      )}
    </div>
  );
}

/* ─── Models Config Tab ──────────────────────────────────────────── */

function ModelsTab({ models, onRefresh }: { models: LlmModelItem[]; onRefresh: () => void }) {
  const [editing, setEditing] = useState<LlmModelItem | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<Record<number, { status: string; response?: string; error?: string; duration_ms: number }>>({});
  const [showAdd, setShowAdd] = useState(false);

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const res = await modelsApi.test(id);
      setTestResult(prev => ({ ...prev, [id]: res }));
    } catch (e: unknown) {
      setTestResult(prev => ({ ...prev, [id]: { status: 'failed', error: String(e), duration_ms: 0 } }));
    }
    setTesting(null);
  };

  const handleSetPrimary = async (id: number) => {
    await modelsApi.setPrimary(id);
    onRefresh();
  };

  const handleSetFallback = async (id: number) => {
    await modelsApi.setFallback(id);
    onRefresh();
  };

  const handleToggle = async (m: LlmModelItem) => {
    await modelsApi.update(m.id, { enabled: !m.enabled });
    onRefresh();
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除该模型配置？')) return;
    await modelsApi.delete(id);
    onRefresh();
  };

  const enabledCount = models.filter(m => m.enabled).length;
  const keyedCount = models.filter(m => m.api_key_set || !m.api_base).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Surface title="模型配置" icon={Settings2} hint={`${models.length} 个模型 · ${enabledCount} 个启用 · ${keyedCount} 个可调用`}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div style={{ fontSize: 13, color: T.gray500, lineHeight: 1.7 }}>
            维护主模型、备用模型和可参与测评的候选模型。禁用模型不会参与自动任务和 A/B 测评。
          </div>
        <button
          onClick={() => setShowAdd(true)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px', fontSize: 13, background: T.primary, color: '#fff', border: 'none', borderRadius: T.radiusSm, cursor: 'pointer', fontWeight: 800, whiteSpace: 'nowrap' }}
        >
          <Plus size={14} strokeWidth={2.2} />
          添加模型
        </button>
        </div>
      </Surface>

      {showAdd && <ModelEditForm onClose={() => { setShowAdd(false); onRefresh(); }} />}

      {editing && <ModelEditForm model={editing} onClose={() => { setEditing(null); onRefresh(); }} />}

      {/* Model Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(420px, 100%), 1fr))', gap: 12 }}>
        {models.map(m => (
          <div key={m.id} style={{
            background: T.white,
            borderRadius: T.radius,
            border: `1px solid ${m.is_primary ? T.primaryBorder : m.is_fallback ? T.tealBorder : T.gray200}`,
            padding: 18,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            opacity: m.enabled ? 1 : 0.62,
            boxShadow: m.is_primary ? '0 12px 28px rgba(255, 107, 53, 0.08)' : 'none',
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 7 }}>
                  {m.is_primary && <StatusPill tone="primary"><Star size={11} fill={T.primary} />主模型</StatusPill>}
                  {m.is_fallback && <StatusPill tone="teal"><ShieldCheck size={11} />备用</StatusPill>}
                  {!m.enabled && <StatusPill>已禁用</StatusPill>}
                  {!m.api_key_set && m.api_base && <StatusPill tone="amber"><KeyRound size={11} />缺 Key</StatusPill>}
                </div>
                <div style={{ fontWeight: 850, fontSize: 16, color: T.gray900, lineHeight: 1.35 }}>{m.name}</div>
                <div style={{ fontSize: 11, color: T.gray400, fontFamily: T.mono, marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {m.model_id}
                </div>
              </div>
              <StatusPill tone={m.enabled ? 'teal' : 'neutral'}>
                <Power size={11} />
                {m.enabled ? '启用' : '停用'}
              </StatusPill>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
              {[
                ['Provider', m.provider],
                ['Temp', m.temperature],
                ['Tokens', m.max_tokens],
                ['RPM', m.requests_per_minute],
              ].map(([label, value]) => (
                <div key={label} style={{ background: T.gray50, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, padding: '8px 9px', minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: T.gray400, marginBottom: 3 }}>{label}</div>
                  <div style={{ fontSize: 12, color: T.gray800, fontWeight: 800, fontFamily: typeof value === 'number' ? T.mono : T.sans, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
              {[
                ['输入未命中', formatPerMillion(m.cost_per_1m_input)],
                ['输出单价', formatPerMillion(m.cost_per_1m_output)],
              ].map(([label, value]) => (
                <div key={label} style={{ background: T.gray50, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, padding: '8px 9px', minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: T.gray400, marginBottom: 3 }}>{label}</div>
                  <div style={{ fontSize: 12, color: value === '未配置' ? T.gray400 : T.gray800, fontWeight: 800, fontFamily: T.mono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div>
                </div>
              ))}
            </div>

            {m.cost_per_1m_input_cache_hit !== null && m.cost_per_1m_input_cache_hit !== undefined && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 10,
                background: T.tealLight,
                border: `1px solid ${T.tealBorder}`,
                borderRadius: T.radiusXs,
                padding: '7px 9px',
                fontSize: 11,
              }}>
                <span style={{ color: T.gray500, fontWeight: 800 }}>输入缓存命中</span>
                <span style={{ color: T.teal, fontWeight: 900, fontFamily: T.mono }}>
                  {formatPerMillion(m.cost_per_1m_input_cache_hit)}
                </span>
              </div>
            )}

            {m.description && (
              <div style={{ fontSize: 12, lineHeight: 1.6, color: T.gray500 }}>
                {m.description}
              </div>
            )}

            {/* Test result */}
            {testResult[m.id] && (
              <div style={{ fontSize: 11, color: testResult[m.id].status === 'success' ? T.teal : T.red, padding: '7px 10px', background: testResult[m.id].status === 'success' ? T.tealLight : T.redLight, border: `1px solid ${testResult[m.id].status === 'success' ? T.tealBorder : '#FCA5A5'}`, borderRadius: T.radiusXs, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {testResult[m.id].status === 'success' ? `${testResult[m.id].duration_ms}ms: ${(testResult[m.id].response || '').slice(0, 40)}...` : `失败: ${(testResult[m.id].error || '').slice(0, 30)}`}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', borderTop: `1px solid ${T.gray100}`, paddingTop: 12 }}>
              {!m.is_primary && <button onClick={() => handleSetPrimary(m.id)} style={actionBtnStyle}>设为主模型</button>}
              {!m.is_primary && !m.is_fallback && <button onClick={() => handleSetFallback(m.id)} style={actionBtnStyle}>设为备用</button>}
              <button onClick={() => handleToggle(m)} style={actionBtnStyle}>{m.enabled ? '禁用' : '启用'}</button>
              <button onClick={() => handleTest(m.id)} disabled={testing === m.id} style={{ ...actionBtnStyle, color: T.primary }}>
                {testing === m.id ? '测试中...' : '测试'}
              </button>
              <button onClick={() => setEditing(m)} style={actionBtnStyle}>编辑</button>
              <button onClick={() => handleDelete(m.id)} style={{ ...actionBtnStyle, color: T.red }}>
                <Trash2 size={12} strokeWidth={2.2} />
                删除
              </button>
            </div>
          </div>
        ))}
      </div>

      {models.length === 0 && (
        <Surface title="空模型库" icon={Settings2}>
        <div style={{ textAlign: 'center', padding: 42, color: T.gray400 }}>
          还没有配置任何模型，点击"添加模型"开始
        </div>
        </Surface>
      )}
    </div>
  );
}

const actionBtnStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5, padding: '6px 10px', fontSize: 12, border: `1px solid ${T.gray200}`, borderRadius: 6,
  background: T.white, color: T.gray600, cursor: 'pointer', whiteSpace: 'nowrap', fontWeight: 700,
};

/* ─── Model Edit/Add Form ────────────────────────────────────────── */

function ModelEditForm({ model, onClose }: { model?: LlmModelItem | null; onClose: () => void }) {
  const isEdit = !!model;
  const initialPreset = PROVIDER_PRESETS[model?.provider || 'openai'] || PROVIDER_PRESETS.openai;
  const [form, setForm] = useState({
    name: model?.name || '',
    provider: model?.provider || 'openai',
    model_id: model?.model_id || '',
    api_key: '',
    api_base: model?.api_base || initialPreset.baseUrl,
    temperature: model?.temperature ?? 0.3,
    max_tokens: model?.max_tokens ?? 2000,
    requests_per_minute: model?.requests_per_minute ?? 60,
    description: model?.description || '',
    enabled: model?.enabled ?? true,
    cost_per_1m_input: model?.cost_per_1m_input?.toString() ?? initialPreset.costPer1MInput?.toString() ?? '',
    cost_per_1m_input_cache_hit: model?.cost_per_1m_input_cache_hit?.toString() ?? initialPreset.costPer1MInputCacheHit?.toString() ?? '',
    cost_per_1m_output: model?.cost_per_1m_output?.toString() ?? initialPreset.costPer1MOutput?.toString() ?? '',
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      payload.cost_per_1m_input = parseOptionalNumber(form.cost_per_1m_input);
      payload.cost_per_1m_input_cache_hit = parseOptionalNumber(form.cost_per_1m_input_cache_hit);
      payload.cost_per_1m_output = parseOptionalNumber(form.cost_per_1m_output);
      if (!payload.api_key) delete payload.api_key;
      if (!payload.api_base) delete payload.api_base;
      if (!payload.description) delete payload.description;
      if (isEdit && model) {
        await modelsApi.update(model.id, payload);
      } else {
        await modelsApi.create(payload);
      }
      onClose();
    } catch (e) { alert('保存失败: ' + String(e)); }
    setSaving(false);
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 12px', fontSize: 13, border: `1px solid ${T.gray200}`,
    borderRadius: T.radiusXs, outline: 'none', boxSizing: 'border-box',
  };

  const handleProviderChange = (provider: string) => {
    const preset = PROVIDER_PRESETS[provider] || PROVIDER_PRESETS.custom;
    const pricing = pricingForProviderModel(provider, form.model_id);
    setForm(f => ({
      ...f,
      provider,
      api_base: preset.baseUrl,
      cost_per_1m_input: pricing?.input?.toString() ?? f.cost_per_1m_input,
      cost_per_1m_input_cache_hit: pricing?.cacheHit?.toString() ?? f.cost_per_1m_input_cache_hit,
      cost_per_1m_output: pricing?.output?.toString() ?? f.cost_per_1m_output,
    }));
  };

  const handleModelIdChange = (modelId: string) => {
    const pricing = pricingForProviderModel(form.provider, modelId);
    setForm(f => ({
      ...f,
      model_id: modelId,
      ...(pricing ? {
        cost_per_1m_input: pricing.input?.toString() ?? f.cost_per_1m_input,
        cost_per_1m_input_cache_hit: pricing.cacheHit?.toString() ?? f.cost_per_1m_input_cache_hit,
        cost_per_1m_output: pricing.output?.toString() ?? f.cost_per_1m_output,
      } : {}),
    }));
  };

  const currentPreset = PROVIDER_PRESETS[form.provider] || PROVIDER_PRESETS.custom;

  return (
    <div style={{
      background: T.white, borderRadius: T.radius, border: `1px solid ${T.primaryBorder}`,
      padding: 20, marginBottom: 2,
      boxShadow: '0 12px 28px rgba(255, 107, 53, 0.08)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Settings2 size={15} color={T.primary} strokeWidth={2.2} />
        <h3 style={{ fontSize: 14, fontWeight: 800, color: T.gray900, margin: 0 }}>{isEdit ? '编辑模型' : '添加模型'}</h3>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>显示名称 *</label>
          <input style={inputStyle} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="如 GLM-5.1" />
        </div>
        <div>
          <label style={labelStyle}>Provider *</label>
          <select style={inputStyle} value={form.provider} onChange={e => handleProviderChange(e.target.value)}>
            {Object.entries(PROVIDER_PRESETS).map(([value, preset]) => (
              <option key={value} value={value}>{preset.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Model ID *</label>
          <input style={inputStyle} value={form.model_id} onChange={e => handleModelIdChange(e.target.value)} placeholder={`如 ${currentPreset.modelPlaceholder}`} />
        </div>
        <div>
          <label style={labelStyle}>API Key {isEdit ? '(留空不修改)' : '*'}</label>
          <input style={inputStyle} type="password" value={form.api_key} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
            <label style={{ ...labelStyle, marginBottom: 0 }}>API Base URL</label>
            {currentPreset.baseUrl && (
              <button
                type="button"
                onClick={() => setForm(f => ({ ...f, api_base: currentPreset.baseUrl }))}
                style={{
                  padding: '1px 7px',
                  borderRadius: 999,
                  border: `1px solid ${T.primaryBorder}`,
                  background: T.primaryLight,
                  color: T.primary,
                  fontSize: 10,
                  fontWeight: 800,
                  cursor: 'pointer',
                }}
              >
                使用内置
              </button>
            )}
          </div>
          <input style={inputStyle} value={form.api_base} onChange={e => setForm(f => ({ ...f, api_base: e.target.value }))} placeholder="https://api.example.com/v1" />
          {currentPreset.baseUrl && (
            <div style={{ marginTop: 4, fontSize: 10, color: T.gray400, lineHeight: 1.45 }}>
              内置默认：{currentPreset.baseUrl}
            </div>
          )}
        </div>
        <div>
          <label style={labelStyle}>描述</label>
          <input style={inputStyle} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="可选备注" />
        </div>
        <div>
          <label style={labelStyle}>Temperature</label>
          <input style={inputStyle} type="number" step="0.1" value={form.temperature} onChange={e => setForm(f => ({ ...f, temperature: parseFloat(e.target.value) || 0.3 }))} />
        </div>
        <div>
          <label style={labelStyle}>Max Tokens</label>
          <input style={inputStyle} type="number" value={form.max_tokens} onChange={e => setForm(f => ({ ...f, max_tokens: parseInt(e.target.value) || 2000 }))} />
        </div>
        <div>
          <label style={labelStyle}>输入未命中单价 / 百万 Tokens</label>
          <input style={inputStyle} type="number" step="0.001" value={form.cost_per_1m_input} onChange={e => setForm(f => ({ ...f, cost_per_1m_input: e.target.value }))} placeholder="如 1" />
        </div>
        <div>
          <label style={labelStyle}>输出单价 / 百万 Tokens</label>
          <input style={inputStyle} type="number" step="0.001" value={form.cost_per_1m_output} onChange={e => setForm(f => ({ ...f, cost_per_1m_output: e.target.value }))} placeholder="如 2" />
        </div>
        <div>
          <label style={labelStyle}>输入缓存命中 / 百万 Tokens</label>
          <input style={inputStyle} type="number" step="0.001" value={form.cost_per_1m_input_cache_hit} onChange={e => setForm(f => ({ ...f, cost_per_1m_input_cache_hit: e.target.value }))} placeholder="如 0.02" />
        </div>
        <div style={{ display: 'flex', alignItems: 'end' }}>
          <div style={{
            width: '100%',
            padding: '8px 10px',
            borderRadius: T.radiusXs,
            border: `1px solid ${currentPreset.pricingNote ? T.tealBorder : T.gray200}`,
            background: currentPreset.pricingNote ? T.tealLight : T.gray50,
            color: currentPreset.pricingNote ? T.teal : T.gray400,
            fontSize: 11,
            lineHeight: 1.45,
          }}>
            {currentPreset.pricingNote || '费用估算按输入未命中价和输出价计算。'}
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button onClick={handleSave} disabled={saving || !form.name || !form.model_id} style={{ padding: '8px 20px', fontSize: 13, background: T.primary, color: '#fff', border: 'none', borderRadius: T.radiusSm, cursor: 'pointer', fontWeight: 800 }}>
          {saving ? '保存中...' : '保存'}
        </button>
        <button onClick={onClose} style={{ padding: '8px 20px', fontSize: 13, background: T.white, color: T.gray600, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, cursor: 'pointer' }}>
          取消
        </button>
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: 'block', fontSize: 12, color: T.gray500, marginBottom: 4, fontWeight: 500 };

/* ─── A/B Evaluate Tab ───────────────────────────────────────────── */

function EvaluateTab({ models }: { models: LlmModelItem[] }) {
  const enabledModels = useMemo(() => models.filter(m => m.enabled), [models]);
  const runnableModelIds = useMemo(
    () => new Set(enabledModels.filter(m => m.api_key_set || !m.api_base).map(m => m.id)),
    [enabledModels]
  );
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [promptType, setPromptType] = useState('analysis');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ eval_run_id: string; results: EvalResult[] } | null>(null);
  const [scoringId, setScoringId] = useState<number | null>(null);

  useEffect(() => {
    setSelected(prev => new Set([...prev].filter(id => runnableModelIds.has(id))));
  }, [models]);

  const toggleModel = (id: number) => {
    if (!runnableModelIds.has(id)) return;
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleRun = async () => {
    if (selected.size < 2) { alert('至少选择 2 个模型进行对比'); return; }
    setRunning(true);
    setResult(null);
    try {
      const res = await modelsApi.runEvaluation({
        model_ids: [...selected],
        prompt_type: promptType,
      });
      // Fetch results
      const detail = await modelsApi.getEvalRun(res.eval_run_id);
      setResult(detail);
    } catch (e) { alert('测评失败: ' + String(e)); }
    setRunning(false);
  };

  const handleScore = async (evalId: number, score: number) => {
    setScoringId(evalId);
    try {
      await modelsApi.scoreEvaluation(evalId, score);
      if (result) {
        setResult({
          ...result,
          results: result.results.map(r => r.id === evalId ? { ...r, quality_score: score } : r),
        });
      }
    } catch (e) {
      alert('评分失败: ' + String(e));
    } finally {
      setScoringId(null);
    }
  };

  const promptTypes = [
    { value: 'analysis', label: '选题分析' },
    { value: 'daily_report', label: 'AI 日报' },
    { value: 'weekly_digest', label: 'AI 周刊' },
    { value: 'classification', label: '内容分类' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Model Selection */}
      <Surface title="选择测评模型" icon={Layers3} hint={`${selected.size} / ${runnableModelIds.size} 已选`}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {enabledModels.map(m => (
            <button
              key={m.id}
              onClick={() => toggleModel(m.id)}
              disabled={!runnableModelIds.has(m.id)}
              style={{
                padding: '9px 13px', fontSize: 13, borderRadius: T.radiusSm, cursor: runnableModelIds.has(m.id) ? 'pointer' : 'not-allowed',
                border: `1px solid ${selected.has(m.id) ? T.primary : T.gray200}`,
                background: selected.has(m.id) ? T.primaryLight : T.white,
                color: !runnableModelIds.has(m.id) ? T.gray400 : selected.has(m.id) ? T.primary : T.gray600,
                fontWeight: selected.has(m.id) ? 800 : 650,
                opacity: runnableModelIds.has(m.id) ? 1 : 0.55,
              }}
              title={runnableModelIds.has(m.id) ? undefined : '该模型缺少 API Key，暂不能参与测评'}
            >
              {m.name}
              {m.is_primary && <span style={{ marginLeft: 4, fontSize: 10 }}>(主)</span>}
              {!runnableModelIds.has(m.id) && <span style={{ marginLeft: 4, fontSize: 10 }}>(缺 Key)</span>}
            </button>
          ))}
        </div>
        {selected.size < 2 && <div style={{ fontSize: 12, color: T.amber, marginTop: 8 }}>请至少选择 2 个模型</div>}
      </Surface>

      {/* Prompt Type */}
      <Surface title="测评任务" icon={FlaskConical}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          {promptTypes.map(pt => (
            <button
              key={pt.value}
              onClick={() => setPromptType(pt.value)}
              style={{
                padding: '7px 12px', fontSize: 13, borderRadius: T.radiusXs, cursor: 'pointer',
                border: `1px solid ${promptType === pt.value ? T.primary : T.gray200}`,
                background: promptType === pt.value ? T.primaryLight : T.white,
                color: promptType === pt.value ? T.primary : T.gray600,
                fontWeight: promptType === pt.value ? 800 : 650,
              }}
            >{pt.label}</button>
          ))}
        </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={running || selected.size < 2}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 7,
          width: 'fit-content',
          padding: '10px 22px', fontSize: 14, fontWeight: 800,
          background: running ? T.gray300 : T.primary, color: '#fff',
          border: 'none', borderRadius: T.radiusSm, cursor: running ? 'not-allowed' : 'pointer',
        }}
      >
        <Play size={15} strokeWidth={2.2} />
        {running ? '测评进行中...' : '开始 A/B 测评'}
      </button>
      </Surface>

      {/* Results */}
      {result && (
        <Surface title="测评结果" icon={CheckCircle2} hint={result.eval_run_id}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(result.results.length, 3)}, minmax(0, 1fr))`, gap: 14 }}>
            {result.results.map(r => (
              <div key={r.id} style={{
                background: T.white, borderRadius: T.radius, border: `1px solid ${r.status === 'DONE' ? T.tealBorder : '#FCA5A5'}`, padding: 16,
                display: 'flex', flexDirection: 'column', gap: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                  <div style={{ fontWeight: 800, fontSize: 14, color: T.gray900 }}>{r.model_name}</div>
                  <StatusPill tone={r.status === 'DONE' ? 'teal' : 'red'}>
                    {r.status === 'DONE' ? '完成' : '失败'}
                  </StatusPill>
                </div>
                <div style={{ fontSize: 12, color: T.gray500 }}>
                  {r.status === 'DONE' ? `${r.duration_ms}ms` : r.error_message?.slice(0, 60)}
                </div>
                {r.tokens_input && (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: T.gray400 }}>
                    Token: {r.tokens_input}
                    <ArrowRight size={12} strokeWidth={2} />
                    {r.tokens_output}
                  </div>
                )}
                {r.response_text && (
                  <div style={{
                    fontSize: 12, color: T.gray700, background: T.gray50, padding: 10,
                    borderRadius: T.radiusXs, maxHeight: 200, overflow: 'auto',
                    whiteSpace: 'pre-wrap', lineHeight: 1.6,
                  }}>{r.response_text}</div>
                )}
                {r.auto_score !== null && <div style={{ fontSize: 11, color: T.gray500 }}>自动评分: {r.auto_score}/5</div>}
                {/* Human score */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: T.gray500 }}>人工评分:</span>
                  {[1, 2, 3, 4, 5].map(s => (
                    <button
                      key={s}
                      onClick={() => handleScore(r.id, s)}
                      disabled={scoringId === r.id}
                      style={{
                        width: 28, height: 28, fontSize: 14,
                        border: `1px solid ${r.quality_score === s ? T.primary : T.gray200}`,
                        background: r.quality_score === s ? T.primaryLight : T.white,
                        color: r.quality_score === s ? T.primary : T.gray500,
                        borderRadius: 6, cursor: 'pointer',
                      }}
                    >{s}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Surface>
      )}
    </div>
  );
}

/* ─── Usage Tab ──────────────────────────────────────────────────── */

function UsageTab({
  usage,
  loading,
  onRefresh,
}: {
  usage: ModelUsageSummary | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  if (loading) return (
    <Surface title="用量统计" icon={BarChart3}>
      <div style={{ textAlign: 'center', color: T.gray400, padding: 48 }}>加载中...</div>
    </Surface>
  );

  if (!usage) return (
    <Surface title="用量统计" icon={BarChart3}>
      <div style={{ textAlign: 'center', color: T.gray400, padding: 48 }}>暂无用量数据</div>
    </Surface>
  );

  const maxModelTokens = Math.max(...usage.by_model.map(item => item.tokens_input + item.tokens_output), 1);
  const maxPromptCost = Math.max(...usage.by_prompt.map(item => item.estimated_cost), 0.000001);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Surface title="30 日用量概览" icon={BarChart3} hint={`自 ${usage.since.slice(0, 10)} 起`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))', gap: 10 }}>
          <StatTile icon={Gauge} label="总 Token" value={formatTokens(usage.total.tokens_total)} hint={`输入 ${formatTokens(usage.total.tokens_input)} · 输出 ${formatTokens(usage.total.tokens_output)}`} color={T.purple} />
          <StatTile icon={Coins} label="费用预估" value={formatCurrency(usage.total.estimated_cost)} hint="按模型配置单价估算" color={T.primary} tone="primary" />
          <StatTile icon={FlaskConical} label="调用次数" value={usage.total.calls} hint={`${usage.total.success_calls} 成功 · ${usage.total.failed_calls} 失败`} color={T.teal} tone="teal" />
          <StatTile icon={Clock3} label="平均耗时" value={`${usage.total.avg_duration_ms}ms`} hint={`成功率 ${(usage.total.success_rate * 100).toFixed(1)}%`} color={T.amber} tone="amber" />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
          <button onClick={onRefresh} style={{ ...actionBtnStyle, color: T.primary }}>
            <RefreshCw size={12} strokeWidth={2.2} />
            刷新用量
          </button>
        </div>
      </Surface>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: 14 }}>
        <Surface title="按模型拆分" icon={Layers3} hint={`${usage.by_model.length} 个模型`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {usage.by_model.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: T.gray400 }}>暂无测评调用记录</div>}
            {usage.by_model.map(item => {
              const totalTokens = item.tokens_input + item.tokens_output;
              const width = Math.max(4, Math.round((totalTokens / maxModelTokens) * 100));
              return (
                <div key={item.model_id} style={{ border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, padding: 12, background: T.white }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 850, color: T.gray900, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.model_name}</div>
                      <div style={{ fontSize: 11, color: T.gray400, marginTop: 3 }}>{item.provider || 'unknown'} · {item.calls} 次调用 · 平均 {item.avg_duration_ms}ms</div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 900, color: T.primary, fontFamily: T.mono }}>{formatCurrency(item.estimated_cost)}</div>
                      <div style={{ fontSize: 10, color: T.gray400, marginTop: 3 }}>{formatTokens(totalTokens)} tokens</div>
                    </div>
                  </div>
                  <div style={{ height: 7, background: T.gray100, borderRadius: 999, overflow: 'hidden', marginTop: 11 }}>
                    <div style={{ width: `${width}%`, height: '100%', background: `linear-gradient(90deg, ${T.primary}, ${T.teal})`, borderRadius: 999 }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginTop: 10 }}>
                    {[
                      ['输入', formatTokens(item.tokens_input)],
                      ['输出', formatTokens(item.tokens_output)],
                      ['成功', item.success_calls],
                      ['失败', item.failed_calls],
                    ].map(([label, value]) => (
                      <div key={label} style={{ background: T.gray50, borderRadius: T.radiusXs, padding: '7px 8px' }}>
                        <div style={{ fontSize: 10, color: T.gray400 }}>{label}</div>
                        <div style={{ marginTop: 3, fontSize: 12, color: T.gray800, fontWeight: 850, fontFamily: T.mono }}>{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Surface>

        <Surface title="按任务类型" icon={SlidersHorizontal} hint={`${usage.by_prompt.length} 类任务`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {usage.by_prompt.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: T.gray400 }}>暂无任务统计</div>}
            {usage.by_prompt.map(item => {
              const width = Math.max(4, Math.round((item.estimated_cost / maxPromptCost) * 100));
              return (
                <div key={item.prompt_type} style={{ borderBottom: `1px solid ${T.gray100}`, paddingBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 850, color: T.gray900 }}>{promptTypeLabel[item.prompt_type] || item.prompt_type}</div>
                      <div style={{ marginTop: 3, fontSize: 11, color: T.gray400 }}>{item.calls} 次 · {formatTokens(item.tokens_input + item.tokens_output)} tokens</div>
                    </div>
                    <div style={{ fontSize: 13, color: T.primary, fontWeight: 900, fontFamily: T.mono }}>{formatCurrency(item.estimated_cost)}</div>
                  </div>
                  <div style={{ height: 6, background: T.gray100, borderRadius: 999, overflow: 'hidden', marginTop: 8 }}>
                    <div style={{ width: `${width}%`, height: '100%', background: T.primary, borderRadius: 999 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Surface>
      </div>
    </div>
  );
}

/* ─── History Tab ────────────────────────────────────────────────── */

function HistoryTab() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<{ results: EvalResult[] } | null>(null);

  useEffect(() => {
    modelsApi.listEvalRuns(30).then(res => { setRuns(res.runs); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const handleExpand = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return; }
    setExpandedRun(runId);
    const detail = await modelsApi.getEvalRun(runId);
    setRunDetail(detail);
  };

  if (loading) return (
    <Surface title="测评历史" icon={History}>
      <div style={{ textAlign: 'center', color: T.gray400, padding: 48 }}>加载中...</div>
    </Surface>
  );

  return (
    <div>
      {runs.length === 0 ? (
        <Surface title="测评历史" icon={History}>
          <div style={{ textAlign: 'center', padding: 48, color: T.gray400 }}>暂无测评记录，去 A/B 测评页开始第一次测评</div>
        </Surface>
      ) : (
        <Surface title="测评历史" icon={History} hint={`${runs.length} 条记录`}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {runs.map(run => (
            <div key={run.eval_run_id}>
              <button
                onClick={() => handleExpand(run.eval_run_id)}
                style={{
                  width: '100%', textAlign: 'left', padding: '12px 16px',
                  background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
                  cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
              >
                <div>
                  <span style={{ fontWeight: 800, fontSize: 13, color: T.gray900 }}>{promptTypeLabel[run.prompt_type] || run.prompt_type}</span>
                  <span style={{ fontSize: 11, color: T.gray400, marginLeft: 8 }}>
                    {run.model_count} 个模型 · {run.created_at?.slice(0, 19).replace('T', ' ')}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <StatusPill tone="teal">{run.done_count} 成功</StatusPill>
                  {run.fail_count > 0 && <StatusPill tone="red">{run.fail_count} 失败</StatusPill>}
                </div>
              </button>
              {expandedRun === run.eval_run_id && runDetail && (
                <div style={{ padding: '8px 16px 16px', background: T.gray50, border: `1px solid ${T.gray200}`, borderTop: 'none', borderRadius: `0 0 ${T.radiusSm}px ${T.radiusSm}px` }}>
                  {runDetail.results.map(r => (
                    <div key={r.id} style={{ display: 'flex', gap: 12, padding: '8px 0', borderBottom: `1px solid ${T.gray100}` }}>
                      <span style={{ fontWeight: 500, fontSize: 13, minWidth: 80 }}>{r.model_name}</span>
                      <span style={{ fontSize: 12, color: r.status === 'DONE' ? T.teal : T.red }}>
                        {r.status} · {r.duration_ms}ms
                      </span>
                      {r.quality_score && <span style={{ fontSize: 12, color: T.primary }}>人工: {r.quality_score}/5</span>}
                      {r.auto_score !== null && <span style={{ fontSize: 12, color: T.gray400 }}>自动: {r.auto_score}/5</span>}
                      {r.error_message && <span style={{ fontSize: 11, color: T.red }} title={r.error_message}>错误</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        </Surface>
      )}
    </div>
  );
}
