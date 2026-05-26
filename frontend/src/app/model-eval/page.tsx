'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { T } from '@/lib/design-tokens';
import { modelsApi } from '@/lib/api';
import type { LlmModelItem, EvalRun, EvalResult } from '@/lib/api';

type Tab = 'models' | 'evaluate' | 'history';

export default function ModelEvalPage() {
  const [tab, setTab] = useState<Tab>('models');
  const [models, setModels] = useState<LlmModelItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchModels = useCallback(async () => {
    try {
      const res = await modelsApi.list();
      setModels(res.models);
    } catch (e) { console.error('fetchModels', e); }
    setLoading(false);
  }, []);

  useEffect(() => { fetchModels(); }, [fetchModels]);

  const tabStyle = (active: boolean) => ({
    padding: '8px 16px',
    fontSize: 13,
    fontWeight: active ? 600 : 400,
    color: active ? T.primary : T.gray500,
    borderWidth: 0,
    borderStyle: 'solid' as const,
    borderColor: 'transparent',
    borderBottomWidth: active ? 2 : 0,
    borderBottomColor: active ? T.primary : 'transparent',
    cursor: 'pointer',
    background: 'none',
  } as React.CSSProperties);

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <span style={{ fontSize: 20 }}>🧪</span>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: T.text, margin: 0 }}>AI 引擎</h1>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, borderBottom: `1px solid ${T.gray200}`, marginBottom: 24 }}>
        <button style={tabStyle(tab === 'models')} onClick={() => setTab('models')}>模型配置</button>
        <button style={tabStyle(tab === 'evaluate')} onClick={() => setTab('evaluate')}>A/B 测评</button>
        <button style={tabStyle(tab === 'history')} onClick={() => setTab('history')}>测评历史</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', color: T.gray400, padding: 60 }}>加载中...</div>
      ) : (
        <>
          {tab === 'models' && <ModelsTab models={models} onRefresh={fetchModels} />}
          {tab === 'evaluate' && <EvaluateTab models={models} />}
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

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: T.gray500 }}>已配置 {models.length} 个模型</span>
        <button
          onClick={() => setShowAdd(true)}
          style={{ padding: '6px 14px', fontSize: 13, background: T.primary, color: '#fff', border: 'none', borderRadius: T.radiusSm, cursor: 'pointer', fontWeight: 600 }}
        >+ 添加模型</button>
      </div>

      {showAdd && <ModelEditForm onClose={() => { setShowAdd(false); onRefresh(); }} />}

      {editing && <ModelEditForm model={editing} onClose={() => { setEditing(null); onRefresh(); }} />}

      {/* Model Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {models.map(m => (
          <div key={m.id} style={{
            background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray200}`,
            padding: 16, display: 'flex', alignItems: 'center', gap: 16,
            opacity: m.enabled ? 1 : 0.5,
          }}>
            {/* Role badge */}
            <div style={{ width: 60, textAlign: 'center', flexShrink: 0 }}>
              {m.is_primary ? (
                <span style={{ fontSize: 11, fontWeight: 600, color: T.primary, background: T.primaryLight, padding: '2px 8px', borderRadius: 4 }}>主模型</span>
              ) : m.is_fallback ? (
                <span style={{ fontSize: 11, fontWeight: 600, color: T.teal, background: T.tealLight, padding: '2px 8px', borderRadius: 4 }}>备用</span>
              ) : (
                <span style={{ fontSize: 11, color: T.gray400 }}>-</span>
              )}
            </div>

            {/* Info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 14, color: T.text }}>{m.name}</span>
                <span style={{ fontSize: 11, color: T.gray400, fontFamily: T.mono }}>{m.model_id}</span>
              </div>
              <div style={{ fontSize: 12, color: T.gray500, marginTop: 4 }}>
                Provider: {m.provider} · Temp: {m.temperature} · MaxTokens: {m.max_tokens} · RPM: {m.requests_per_minute}
                {m.description && ` · ${m.description}`}
              </div>
            </div>

            {/* Test result */}
            {testResult[m.id] && (
              <div style={{ maxWidth: 200, fontSize: 11, color: testResult[m.id].status === 'success' ? T.teal : T.red, padding: '4px 8px', background: testResult[m.id].status === 'success' ? T.tealLight : T.redLight, borderRadius: T.radiusXs, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {testResult[m.id].status === 'success' ? `${testResult[m.id].duration_ms}ms: ${(testResult[m.id].response || '').slice(0, 40)}...` : `失败: ${(testResult[m.id].error || '').slice(0, 30)}`}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              {!m.is_primary && <button onClick={() => handleSetPrimary(m.id)} style={actionBtnStyle}>设为主模型</button>}
              {!m.is_primary && !m.is_fallback && <button onClick={() => handleSetFallback(m.id)} style={actionBtnStyle}>设为备用</button>}
              <button onClick={() => handleToggle(m)} style={actionBtnStyle}>{m.enabled ? '禁用' : '启用'}</button>
              <button onClick={() => handleTest(m.id)} disabled={testing === m.id} style={{ ...actionBtnStyle, color: T.primary }}>
                {testing === m.id ? '测试中...' : '测试'}
              </button>
              <button onClick={() => setEditing(m)} style={actionBtnStyle}>编辑</button>
              <button onClick={() => handleDelete(m.id)} style={{ ...actionBtnStyle, color: T.red }}>删除</button>
            </div>
          </div>
        ))}
      </div>

      {models.length === 0 && (
        <div style={{ textAlign: 'center', padding: 60, color: T.gray400 }}>
          还没有配置任何模型，点击"添加模型"开始
        </div>
      )}
    </div>
  );
}

const actionBtnStyle: React.CSSProperties = {
  padding: '4px 10px', fontSize: 12, border: `1px solid ${T.gray200}`, borderRadius: 6,
  background: T.white, color: T.gray600, cursor: 'pointer', whiteSpace: 'nowrap',
};

/* ─── Model Edit/Add Form ────────────────────────────────────────── */

function ModelEditForm({ model, onClose }: { model?: LlmModelItem | null; onClose: () => void }) {
  const isEdit = !!model;
  const [form, setForm] = useState({
    name: model?.name || '',
    provider: model?.provider || 'openai',
    model_id: model?.model_id || '',
    api_key: '',
    api_base: model?.api_base || '',
    temperature: model?.temperature ?? 0.3,
    max_tokens: model?.max_tokens ?? 2000,
    requests_per_minute: model?.requests_per_minute ?? 60,
    description: model?.description || '',
    enabled: model?.enabled ?? true,
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = { ...form };
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

  return (
    <div style={{
      background: T.gray50, borderRadius: T.radius, border: `1px solid ${T.gray200}`,
      padding: 20, marginBottom: 16,
    }}>
      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 16px' }}>{isEdit ? '编辑模型' : '添加模型'}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>显示名称 *</label>
          <input style={inputStyle} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="如 GLM-5.1" />
        </div>
        <div>
          <label style={labelStyle}>Provider *</label>
          <select style={inputStyle} value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value }))}>
            <option value="openai">openai</option>
            <option value="custom">custom</option>
            <option value="deepseek">deepseek</option>
            <option value="minimax">minimax</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Model ID *</label>
          <input style={inputStyle} value={form.model_id} onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))} placeholder="如 openai/glm-5.1" />
        </div>
        <div>
          <label style={labelStyle}>API Key {isEdit ? '(留空不修改)' : '*'}</label>
          <input style={inputStyle} type="password" value={form.api_key} onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
        </div>
        <div>
          <label style={labelStyle}>API Base URL</label>
          <input style={inputStyle} value={form.api_base} onChange={e => setForm(f => ({ ...f, api_base: e.target.value }))} placeholder="https://api.example.com/v1" />
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
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button onClick={handleSave} disabled={saving || !form.name || !form.model_id} style={{ padding: '8px 20px', fontSize: 13, background: T.primary, color: '#fff', border: 'none', borderRadius: T.radiusSm, cursor: 'pointer', fontWeight: 600 }}>
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
    <div>
      {/* Model Selection */}
      <div style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>选择要对比的模型</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {enabledModels.map(m => (
            <button
              key={m.id}
              onClick={() => toggleModel(m.id)}
              disabled={!runnableModelIds.has(m.id)}
              style={{
                padding: '8px 14px', fontSize: 13, borderRadius: T.radiusSm, cursor: runnableModelIds.has(m.id) ? 'pointer' : 'not-allowed',
                border: `1px solid ${selected.has(m.id) ? T.primary : T.gray200}`,
                background: selected.has(m.id) ? T.primaryLight : T.white,
                color: !runnableModelIds.has(m.id) ? T.gray400 : selected.has(m.id) ? T.primary : T.gray600,
                fontWeight: selected.has(m.id) ? 600 : 400,
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
      </div>

      {/* Prompt Type */}
      <div style={{ marginBottom: 20 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>测评类型</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          {promptTypes.map(pt => (
            <button
              key={pt.value}
              onClick={() => setPromptType(pt.value)}
              style={{
                padding: '6px 12px', fontSize: 13, borderRadius: T.radiusXs, cursor: 'pointer',
                border: `1px solid ${promptType === pt.value ? T.primary : T.gray200}`,
                background: promptType === pt.value ? T.primaryLight : T.white,
                color: promptType === pt.value ? T.primary : T.gray600,
              }}
            >{pt.label}</button>
          ))}
        </div>
      </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={running || selected.size < 2}
        style={{
          padding: '10px 28px', fontSize: 14, fontWeight: 600,
          background: running ? T.gray300 : T.primary, color: '#fff',
          border: 'none', borderRadius: T.radiusSm, cursor: running ? 'not-allowed' : 'pointer',
        }}
      >{running ? '测评进行中...' : '开始 A/B 测评'}</button>

      {/* Results */}
      {result && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
            测评结果 <span style={{ fontSize: 12, color: T.gray400, fontWeight: 400 }}>{result.eval_run_id}</span>
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(result.results.length, 3)}, 1fr)`, gap: 16 }}>
            {result.results.map(r => (
              <div key={r.id} style={{
                background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray200}`, padding: 16,
                display: 'flex', flexDirection: 'column', gap: 8,
              }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: T.text }}>{r.model_name}</div>
                <div style={{ fontSize: 12, color: r.status === 'DONE' ? T.teal : T.red }}>
                  {r.status === 'DONE' ? `完成 · ${r.duration_ms}ms` : `失败 · ${r.error_message?.slice(0, 60)}`}
                </div>
                {r.tokens_input && <div style={{ fontSize: 11, color: T.gray400 }}>Token: {r.tokens_input} → {r.tokens_output}</div>}
                {r.response_text && (
                  <div style={{
                    fontSize: 12, color: T.gray700, background: T.gray50, padding: 10,
                    borderRadius: T.radiusXs, maxHeight: 200, overflow: 'auto',
                    whiteSpace: 'pre-wrap', lineHeight: 1.6,
                  }}>{r.response_text}</div>
                )}
                {r.auto_score !== null && <div style={{ fontSize: 11, color: T.gray500 }}>自动评分: {r.auto_score}/5</div>}
                {/* Human score */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
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
        </div>
      )}
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

  const promptTypeLabel: Record<string, string> = {
    analysis: '选题分析', daily_report: 'AI 日报', weekly_digest: 'AI 周刊', classification: '内容分类', custom: '自定义',
  };

  if (loading) return <div style={{ textAlign: 'center', color: T.gray400, padding: 60 }}>加载中...</div>;

  return (
    <div>
      {runs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: T.gray400 }}>暂无测评记录，去 A/B 测评页开始第一次测评</div>
      ) : (
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
                  <span style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{promptTypeLabel[run.prompt_type] || run.prompt_type}</span>
                  <span style={{ fontSize: 11, color: T.gray400, marginLeft: 8 }}>
                    {run.model_count} 个模型 · {run.created_at?.slice(0, 19).replace('T', ' ')}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{ fontSize: 11, color: T.teal }}>{run.done_count} 成功</span>
                  {run.fail_count > 0 && <span style={{ fontSize: 11, color: T.red }}>{run.fail_count} 失败</span>}
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
      )}
    </div>
  );
}
