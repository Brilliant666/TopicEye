'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthContext } from '@/providers/AppProvider';
import { discoverOperationsApi, discoverOperationLabel, type DiscoverPlan, type DiscoverOperation } from '@/lib/api/discover-operations';
import styles from './RardarNewsOperations.module.css';

export default function RardarDiscoverOperations() {
  const { currentUser, authLoading } = useAuthContext();
  if (authLoading) return null;
  if (!currentUser) return <p className={styles.login}><Link href="/login">管理员登录</Link>后可生成下一批精选</p>;
  if (currentUser.role !== 'admin') return null;
  return <AdminOperations key={currentUser.id} userId={currentUser.id} />;
}

function AdminOperations({ userId }: { userId: number }) {
  const router = useRouter();
  const [operation, setOperation] = useState<DiscoverOperation | null>(null);
  const [plan, setPlan] = useState<DiscoverPlan | null>(null);
  const [ready, setReady] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const revision = useRef(0);
  const previous = useRef<DiscoverOperation | null>(null);
  const refreshed = useRef<string | null>(null);
  const storageKey = `rardar-discover-pending-${userId}`;
  const active = operation?.status === 'running';
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const requestedRevision = revision.current;
        const state = await discoverOperationsApi.current();
        if (cancelled) return;
        if (inFlight.current || revision.current !== requestedRevision) {
          timer = setTimeout(poll, 3000);
          return;
        }
        const next = state.latest;
        if (previous.current?.id === next?.id && previous.current?.status === 'running' && next?.status !== 'running' && refreshed.current !== next?.id) {
          refreshed.current = next?.id ?? null;
          router.refresh();
        }
        previous.current = next;
        setOperation(next);
        if (state.prepared !== undefined) setPlan(state.prepared);
        setReady(true);
      } catch { if (!cancelled) setError('暂时无法读取操作状态，现有精选仍可阅读。'); }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [router]);

  async function submit(confirm: boolean, recheck = false) {
    if (!ready || active || inFlight.current || (confirm && !plan)) return;
    inFlight.current = true;
    revision.current += 1;
    setSending(true);
    setError('');
    const key = `${storageKey}-${confirm ? plan!.id : 'prepare'}`;
    try {
      const saved = recheck ? null : sessionStorage.getItem(key);
      const requestId = saved && /^[0-9a-f-]{36}$/i.test(saved) ? saved : crypto.randomUUID();
      sessionStorage.setItem(key, requestId);
      if (confirm) {
        const next = await discoverOperationsApi.start(requestId, plan!.id);
        previous.current = next;
        setOperation(next);
        setPlan(null);
        if (next.status !== 'running' && refreshed.current !== next.id) { refreshed.current = next.id; router.refresh(); }
      } else setPlan(await discoverOperationsApi.prepare(requestId));
      sessionStorage.removeItem(key);
    } catch { setError('操作结果暂未确认；再次点击会确认同一次操作，不会自动扩额或换项目。'); }
    finally { inFlight.current = false; setSending(false); }
  }
  return <section className={styles.panel} style={{ overflowWrap: 'anywhere' }} aria-label="管理员精选更新">
    <div className={styles.heading}>
      <div><h2>下一批精选</h2><p>先查看固定候选和请求上限，确认后才开始评估。当前精选在构建期间保持可读。</p></div>
      <div className={styles.actions}><button type="button" disabled={!ready || sending || active || Boolean(plan)} onClick={() => void submit(false)}>生成下一批精选</button></div>
    </div>
    {error && <p role="alert">{error}</p>}
    {plan && !active && <div className={styles.confirm}>
      <DiscoverPlanDetails plan={plan} />
      {plan.candidateCount === 0 && <p>当前没有待评估候选，本次不会发出模型请求。</p>}
      <p>全部阶段和重试共用此上限；失败不会自动补位或扩额。准备候选不调用模型。</p>
      <div className={styles.actions}>
        <button type="button" disabled={sending || plan.candidateCount === 0} onClick={() => void submit(true)}>确认评估本批（最多 {plan.requestLimit} 次请求）</button>
        <button type="button" disabled={sending} onClick={() => void submit(false, true)}>重新检查候选</button>
      </div>
      <p>来源或配置变化时可重新检查未执行计划；不会开始评估，也不会推进批次。</p>
    </div>}
    {operation && <DiscoverOperationResult operation={operation} />}
  </section>;
}

export function DiscoverPlanDetails({ plan }: { plan: DiscoverPlan }) {
  return <div><p>本次固定 {plan.candidateCount} 项 · 模型请求上限 {plan.requestLimit} 次</p>
    <p>事实时间：{plan.latestCaptureAt ? new Date(plan.latestCaptureAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '未知'}</p>
    <details><summary>查看候选与绑定版本</summary><p>来源：{plan.sourceObservationSetId}</p><p>Today：{plan.todayGenerationId}</p><ul>{plan.candidates.map((item) => <li key={item.githubRepositoryId}>{item.repository}</li>)}</ul></details>
  </div>;
}
export function DiscoverOperationResult({ operation }: { operation: DiscoverOperation }) {
  const errorCode = safeCode(operation.errorCode);
  const stopReason = safeCode(operation.result?.stopReason);
  return <div className={styles.result} aria-live="polite">
    <strong>{discoverOperationLabel(operation.status)}</strong>
    <p>固定候选 {operation.plan.candidateCount} 项 · 已用请求 {operation.providerCalls}/{operation.plan.requestLimit}</p>
    {operation.status === 'running' && <p>可以离开或刷新页面查看进度，不会自动再次启动。</p>}
    {['failed', 'interrupted', 'not_configured'].includes(operation.status) && <p>现有精选保留，未自动重试或扩大预算；未完成项目不等于不值得看。</p>}
    {errorCode && <p>操作状态码：<code>{errorCode}</code></p>}
    {operation.result && <>
      {operation.result.stopped && <p>连续同类错误，已停止新增请求；已完成的安全结果保留。{stopReason && <> 状态码：<code>{stopReason}</code></>}</p>}
      <p>已处理 {operation.result.processedCount} 项 · 发布 {operation.result.publishedCount} 项 · 未完成 {operation.result.failedCount} 项 · 缓存复用 {operation.result.cacheHits}</p>
      <p>{operation.result.installed ? '本批结果已安装' : '现有精选未替换'}</p>
      {operation.result.failures.length > 0 && <details><summary>查看逐项未完成原因</summary><ul>{operation.result.failures.map((item) => <li key={item.repository}>{item.repository}：{item.reason}</li>)}</ul></details>}
    </>}
    <DiscoverPlanDetails plan={operation.plan} />
  </div>;
}

function safeCode(value: string | null | undefined): string | null {
  return value && /^[a-z][a-z0-9_]{0,99}$/.test(value) ? value : null;
}
