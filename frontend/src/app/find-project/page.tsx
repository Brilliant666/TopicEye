'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { AlertTriangle, ArrowRight, CheckCircle2, Code2, Loader2, RotateCcw, Search, SlidersHorizontal, Sparkles } from 'lucide-react';
import { rardarRequest } from '@/lib/rardar-api';

type RequirementProfile = {
  goal: string;
  mustHave: string[];
  niceToHave: string[];
  constraints: string[];
  exclude: string[];
  technologyStack: string[];
  deployment: string[];
  licensePreference: string[];
  reuseGranularity: string[];
  acceptanceCriteria: string[];
  repositoryContext: string | null;
};

type QuickCandidate = {
  projectId: string;
  repository: string;
  summaryZh: string;
  capabilities: string[];
};

type MatchedCandidate = {
  projectId: string;
  repository: string;
  summaryZh: string;
  whyMatched: string;
  mustHaveCoverage: string[];
  missingCapabilities: string[];
  unknownCapabilities: string[];
  technicalCompatibility: string;
  reuseType: string;
  referenceKinds: string[];
  integrationCost: string;
  integrationWorkItems: string[];
  engineeringEvidence: Array<{ label: string; kind: string; url: string }>;
  licenseAndRisk: string;
  evidenceRefs: string[];
  confidence: number;
  nextValidationAction: string;
};

type FindJob = {
  jobId: string;
  state: string;
  stateHistory: Array<{ state: string; detail: string; at: string }>;
  requirementProfile: RequirementProfile | null;
  confirmedRequirementProfile: RequirementProfile | null;
  quickCandidates: QuickCandidate[] | null;
  result: { candidates: MatchedCandidate[]; sourceRevision: string } | null;
  candidateFixtureRevision: string;
  explosionArtifactRevision: string;
  attemptCount: number;
  errorCode: string | null;
  errorMessage: string | null;
};

const terminalStates = new Set(['quick_candidates_ready', 'ready', 'failed']);

export default function FindProjectPage() {
  return <Suspense fallback={<LoadingCard label="正在准备找项目工作台" />}><FindProjectWorkspace /></Suspense>;
}

function FindProjectWorkspace() {
  const params = useSearchParams();
  const [query, setQuery] = useState('我需要一个可自托管、能编排任务并保留审计证据的开发者平台');
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [scenario, setScenario] = useState('success');
  const [job, setJob] = useState<FindJob | null>(null);
  const [profile, setProfile] = useState<RequirementProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadJob = useCallback(async (jobId: string) => {
    const current = await rardarRequest<FindJob>(`/find-jobs/${jobId}`);
    setJob(current);
    if (current.requirementProfile && !profile) setProfile(current.requirementProfile);
    return current;
  }, [profile]);

  useEffect(() => {
    const jobId = params.get('jobId');
    if (jobId && !job) void loadJob(jobId).catch((error) => setMessage(String(error)));
  }, [job, loadJob, params]);

  useEffect(() => {
    if (!job || terminalStates.has(job.state)) return;
    const timer = window.setTimeout(() => {
      void loadJob(job.jobId).catch((error) => setMessage(String(error)));
    }, 650);
    return () => window.clearTimeout(timer);
  }, [job, loadJob]);

  const createJob = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const created = await rardarRequest<FindJob>('/find-jobs', {
        method: 'POST',
        body: JSON.stringify({
          query,
          repositoryUrl: repositoryUrl.trim() || null,
          scenario,
        }),
      });
      setJob(created);
      setProfile(null);
      window.history.replaceState(null, '', `/find-project?jobId=${encodeURIComponent(created.jobId)}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!job || !profile) return;
    setBusy(true);
    try {
      const updated = await rardarRequest<FindJob>(`/find-jobs/${job.jobId}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ requirementProfile: profile }),
      });
      setJob(updated);
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await rardarRequest<FindJob>(`/find-jobs/${job.jobId}/retry`, { method: 'POST' }));
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-8 sm:px-7 lg:px-10 lg:py-12">
      <section className="overflow-hidden rounded-[30px] border border-blue-100 bg-white p-6 shadow-[0_24px_80px_rgba(37,99,235,0.08)] sm:p-9 lg:p-11">
        <div className="grid gap-8 lg:grid-cols-[1fr_360px] lg:items-end">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1.5 text-xs font-black text-blue-700"><Search size={14} /> Find Project v2 · vertical POC</div>
            <h1 className="mt-5 text-4xl font-black tracking-[-0.04em] sm:text-5xl">少走弯路，先找到<span className="text-blue-600">可以复用的项目</span></h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-500">自然语言需求可以单独提交，也可以附带一个公开 GitHub 仓库。候选只来自版本化 fixture，模型不生成仓库。</p>
          </div>
          <div className="rounded-2xl border border-blue-100 bg-blue-50/70 p-4 text-xs leading-6 text-slate-600">
            <p className="font-black text-blue-800">纵向切片状态</p>
            <p>PostgreSQL durable Job · 独立 Worker · Mock Sub2API · 本地 Schema 验证</p>
          </div>
        </div>
      </section>

      <div className="mt-7 grid gap-7 lg:grid-cols-[minmax(0,1fr)_330px]">
        <div className="space-y-6">
          {!job && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
              <label className="block text-sm font-black text-slate-800" htmlFor="find-query">你正在做什么？</label>
              <textarea id="find-query" value={query} onChange={(event) => setQuery(event.target.value)} rows={5} className="mt-3 w-full resize-none rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              <label className="mt-5 block text-sm font-black text-slate-800" htmlFor="repo-url"><Code2 size={15} className="mr-1.5 inline" />公开 GitHub 仓库 URL <span className="font-medium text-slate-400">（可选）</span></label>
              <input id="repo-url" value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} placeholder="https://github.com/owner/repository" className="mt-3 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <select aria-label="POC 场景" value={scenario} onChange={(event) => setScenario(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-500">
                  <option value="success">成功场景</option><option value="job_fail_once">首次失败后可重试</option><option value="timeout">Provider timeout</option><option value="429">Provider 429</option><option value="5xx">Provider 5xx</option><option value="invalid_json">Invalid JSON</option><option value="schema_mismatch">Schema mismatch</option>
                </select>
                <button type="button" disabled={busy || query.trim().length < 6} onClick={createJob} className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">{busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} 建立需求画像</button>
              </div>
            </section>
          )}

          {job && !terminalStates.has(job.state) && <LoadingCard label={stateLabel(job.state)} />}

          {job?.state === 'quick_candidates_ready' && profile && (
            <section className="rounded-2xl border border-blue-200 bg-white p-5 shadow-sm sm:p-7" data-testid="requirement-confirmation">
              <div className="flex items-center gap-2 text-blue-700"><SlidersHorizontal size={18} /><h2 className="font-black">确认 RequirementProfile</h2></div>
              <p className="mt-2 text-sm text-slate-500">这是 high 推导结果。你可以编辑，确认后才进入 xhigh 的 5→3 横向比较。</p>
              <ProfileEditor profile={profile} onChange={setProfile} />
              <button type="button" disabled={busy} onClick={confirm} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white hover:bg-blue-700 disabled:opacity-50">确认并深度比较 <ArrowRight size={16} /></button>
            </section>
          )}

          {job?.state === 'quick_candidates_ready' && (
            <section>
              <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-black">快速候选 · 5</h2><span className="font-mono text-[11px] text-slate-400">{job.candidateFixtureRevision}</span></div>
              <div className="grid gap-3 sm:grid-cols-2">
                {job.quickCandidates?.map((candidate) => <QuickCandidate key={candidate.projectId} candidate={candidate} />)}
              </div>
            </section>
          )}

          {job?.state === 'ready' && job.result && (
            <section data-testid="find-results">
              <div className="mb-4"><p className="text-xs font-black uppercase tracking-[0.18em] text-emerald-600">Deep comparison ready</p><h2 className="mt-1 text-2xl font-black">3 个可执行的复用方向</h2></div>
              <div className="space-y-4">{job.result.candidates.map((candidate, index) => <ResultCandidate key={candidate.projectId} candidate={candidate} index={index} />)}</div>
            </section>
          )}

          {job?.state === 'failed' && (
            <section className="rounded-2xl border border-red-200 bg-red-50 p-6" data-testid="find-failed"><div className="flex items-center gap-2 font-black text-red-700"><AlertTriangle size={18} />本次分析失败，但 Job 与事实 artifact 都已保留</div><p className="mt-2 text-sm text-red-600">{job.errorCode}: {job.errorMessage}</p><button type="button" disabled={busy} onClick={retry} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-black text-white"><RotateCcw size={15} />重试</button></section>
          )}

          {message && <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-700">{message}</p>}
        </div>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-black">Job 进度</h2>
            {job ? <ol className="mt-4 space-y-4">{job.stateHistory.map((event, index) => <li key={`${event.at}-${index}`} className="grid grid-cols-[22px_1fr] gap-2"><span className="mt-0.5 grid h-5 w-5 place-items-center rounded-full bg-blue-50 text-blue-600"><CheckCircle2 size={12} /></span><div><p className="text-xs font-black text-slate-700">{stateLabel(event.state)}</p><p className="mt-1 text-[11px] leading-5 text-slate-400">{event.detail}</p></div></li>)}</ol> : <p className="mt-3 text-xs leading-5 text-slate-400">提交需求后会显示每个持久状态；刷新页面不会丢失。</p>}
          </section>
          {job && <section className="rounded-2xl border border-slate-200 bg-slate-950 p-5 font-mono text-[11px] leading-6 text-slate-300"><p className="font-bold text-cyan-300">CONTROL PLANE</p><p className="mt-2 break-all">job: {job.jobId}</p><p>attempts: {job.attemptCount}</p><p>artifact: {job.explosionArtifactRevision}</p><p>fixture: {job.candidateFixtureRevision}</p></section>}
        </aside>
      </div>
    </div>
  );
}

function ProfileEditor({ profile, onChange }: { profile: RequirementProfile; onChange: (value: RequirementProfile) => void }) {
  const fields: Array<[keyof RequirementProfile, string]> = [
    ['mustHave', '必须能力'], ['niceToHave', '偏好能力'], ['constraints', '约束'],
    ['exclude', '排除项'], ['technologyStack', '技术栈'], ['deployment', '部署'],
    ['licensePreference', '许可证偏好'], ['reuseGranularity', '复用粒度'],
    ['acceptanceCriteria', '验收标准'],
  ];
  const updateList = (key: keyof RequirementProfile, raw: string) => onChange({ ...profile, [key]: raw.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean) });
  return <div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="sm:col-span-2 text-xs font-black text-slate-600">目标<input value={profile.goal} onChange={(event) => onChange({ ...profile, goal: event.target.value })} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-medium outline-none focus:border-blue-400" /></label>{fields.map(([key, label]) => <label key={key} className="text-xs font-black text-slate-600">{label}<textarea rows={3} value={(profile[key] as string[]).join('，')} onChange={(event) => updateList(key, event.target.value)} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-medium leading-5 outline-none focus:border-blue-400" /></label>)}</div>;
}

function QuickCandidate({ candidate }: { candidate: QuickCandidate }) { return <article className="rounded-xl border border-slate-200 bg-white p-4"><p className="font-black">{candidate.repository}</p><p className="mt-1 text-xs leading-5 text-slate-500">{candidate.summaryZh}</p><div className="mt-3 flex flex-wrap gap-1">{candidate.capabilities.map((item) => <span key={item} className="rounded bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500">{item}</span>)}</div></article>; }

function ResultCandidate({ candidate, index }: { candidate: MatchedCandidate; index: number }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-xs font-black text-blue-600">#{index + 1} · {candidate.reuseType}</p><h3 className="mt-1 text-xl font-black">{candidate.repository}</h3><p className="mt-2 max-w-3xl text-xs leading-5 text-slate-500">{candidate.summaryZh}</p></div>
      <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-black text-emerald-700">置信 {Math.round(candidate.confidence * 100)}%</span>
    </div>
    <p className="mt-4 text-sm leading-6 text-slate-700">{candidate.whyMatched}</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-3">
      <EvidenceGroup title="Must-have 已覆盖" values={candidate.mustHaveCoverage} tone="blue" />
      <EvidenceGroup title="缺失能力" values={candidate.missingCapabilities} tone="amber" />
      <EvidenceGroup title="未知能力" values={candidate.unknownCapabilities} tone="slate" />
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <div className="rounded-xl bg-blue-50 p-4 text-xs leading-6 text-blue-950"><b>技术兼容</b><p>{candidate.technicalCompatibility}</p><p className="mt-2"><b>集成成本：</b>{candidate.integrationCost}</p><ul className="mt-1 list-inside list-disc">{candidate.integrationWorkItems.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <div className="rounded-xl bg-amber-50 p-4 text-xs leading-6 text-amber-950"><b>许可证与风险</b><p>{candidate.licenseAndRisk}</p><p className="mt-2"><b>参考类型：</b>{candidate.referenceKinds.length ? candidate.referenceKinds.join(' · ') : '不适用'}</p></div>
    </div>
    <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600">
      <summary className="cursor-pointer font-black text-slate-800">工程证据与 evidenceRefs</summary>
      <ul className="mt-3 space-y-2">{candidate.engineeringEvidence.map((evidence) => <li key={`${evidence.kind}-${evidence.url}`}><a className="font-bold text-blue-700 underline decoration-blue-200 underline-offset-2" href={evidence.url} target="_blank" rel="noreferrer">{evidence.label}</a><span className="ml-2 text-slate-400">{evidence.kind}</span></li>)}</ul>
      <p className="mt-3 break-all font-mono text-[10px] leading-5 text-slate-400">{candidate.evidenceRefs.join(' · ')}</p>
    </details>
    <div className="mt-4 rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100"><b className="text-cyan-300">下一验证动作：</b>{candidate.nextValidationAction}</div>
  </article>;
}

function EvidenceGroup({ title, values, tone }: { title: string; values: string[]; tone: 'blue' | 'amber' | 'slate' }) {
  const styles = { blue: 'bg-blue-50 text-blue-950', amber: 'bg-amber-50 text-amber-950', slate: 'bg-slate-50 text-slate-700' };
  return <div className={`rounded-xl p-3 text-xs leading-5 ${styles[tone]}`}><b>{title}</b><p className="mt-1">{values.length ? values.join(' · ') : '无'}</p></div>;
}

function LoadingCard({ label }: { label: string }) { return <section className="grid min-h-64 place-items-center rounded-2xl border border-blue-100 bg-white p-8 text-center shadow-sm"><div><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-blue-600"><Loader2 size={24} className="animate-spin" /></span><p className="mt-4 font-black">{label}</p><p className="mt-2 text-xs text-slate-400">独立 Worker 正在处理；页面刷新不会取消 Job。</p></div></section>; }

function stateLabel(state: string) { return ({ queued: '已排队', parsing_requirement: '解析需求', quick_candidates_ready: '快速候选已就绪', deep_analysis: '深度横向比较', ready: '结果已就绪', failed: '处理失败' } as Record<string, string>)[state] || state; }
