'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthContext } from '@/providers/AppProvider';
import { newsOperationsApi, newsOperationLabel, type NewsOperation, type NewsOperationInput } from '@/lib/api/news-operations';
import styles from './RardarNewsOperations.module.css';

type Scope = { source: string | null; topic: string | null; sort: 'balanced' | 'latest'; page: number; itemCount: number };

export default function RardarNewsOperations(scope: Scope) {
  const { currentUser, authLoading } = useAuthContext();
  if (authLoading) return null;
  if (!currentUser) return <p className={styles.login}><Link href="/login">管理员登录</Link>后可更新资讯与补充中文速读</p>;
  if (currentUser.role !== 'admin') return null;
  return <AdminOperations {...scope} userId={currentUser.id} key={currentUser.id} />;
}

function AdminOperations(scope: Scope & { userId: number }) {
  const router = useRouter();
  const [operation, setOperation] = useState<NewsOperation | null>(null);
  const [limits, setLimits] = useState<{ requestLimit: number; pageSize: number } | null>(null);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState<NewsOperationInput | null>(null);
  const inFlight = useRef(false);
  const lastStatus = useRef<string | null>(null);
  const active = operation?.status === 'running';
  const storageKey = `rardar-news-pending-${scope.userId}`;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const saved = sessionStorage.getItem(storageKey);
        if (saved) {
          const input = JSON.parse(saved) as NewsOperationInput;
          if (typeof input.requestId === 'string' && ['refresh', 'enhance'].includes(input.action)) setPending(input);
        }
        const state = await newsOperationsApi.current();
        if (cancelled) return;
        setLimits(state);
        if (lastStatus.current === 'running' && state.latest?.status !== 'running') router.refresh();
        lastStatus.current = state.latest?.status ?? null;
        setOperation(state.latest);
        setError('');
      } catch {
        if (!cancelled) setError('暂时无法读取操作状态；请稍后重试，已保存内容不受影响。');
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [router, storageKey]);

  async function start(action: NewsOperationInput['action']) {
    if (inFlight.current || active || !limits) return;
    inFlight.current = true;
    setSending(true);
    setError('');
    // A transport retry preserves the exact operation identity and frozen query.
    const input = pending ?? {
      action, requestId: crypto.randomUUID(), sort: scope.sort, page: scope.page,
      ...(scope.source ? { source: scope.source } : {}), ...(scope.topic ? { topic: scope.topic } : {}),
    };
    setPending(input);
    try {
      // Persist only a non-secret request identity/query before sending. A reload
      // can retry this exact operation instead of minting a fresh budget.
      sessionStorage.setItem(storageKey, JSON.stringify(input));
      const result = await newsOperationsApi.start(input);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      lastStatus.current = result.status;
      setOperation(result);
      setConfirming(false);
      if (result.status !== 'running') router.refresh();
    } catch {
      setError('提交结果暂未确认。再次点击将查询同一次操作，不会重新获得额度。');
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  return <section className={styles.panel} aria-label="管理员资讯更新">
    <div className={styles.heading}><div><h2>资讯更新</h2><p>管理员操作 · 浏览和状态查询不会抓取来源或调用模型</p></div>
      <div className={styles.actions}>
        <button type="button" disabled={!limits || sending || active || Boolean(pending)} onClick={() => void start('refresh')}>更新资讯 · 不调用模型</button>
        <button type="button" disabled={!limits || sending || active || !scope.itemCount || Boolean(pending)} onClick={() => setConfirming(true)}>补充中文速读</button>
      </div>
    </div>
    {confirming && <div className={styles.confirm}>
      <p>处理当前筛选第 {scope.page} 页，启动时固定最多 {Math.min(scope.itemCount, limits?.pageSize ?? 18)} 条；优先复用原生中文和缓存。</p>
      <p>本次模型请求最多 <strong>{limits?.requestLimit}</strong> 次（含失败与重试），可能产生费用。达到上限即停止，不自动扩额。</p>
      <div className={styles.actions}><button type="button" disabled={sending || active} onClick={() => void start('enhance')}>确认补充中文</button><button type="button" disabled={sending} onClick={() => setConfirming(false)}>取消</button></div>
    </div>}
    {error && <p role="alert">{error}</p>}
    {pending && !sending && <button type="button" disabled={active} onClick={() => void start(pending.action)}>确认上次提交结果（同一次操作）</button>}
    {operation && <div className={styles.result} aria-live="polite">
      <strong>{operation.action === 'refresh' ? '资讯更新' : '中文速读'} · {newsOperationLabel(operation.status)}</strong>
      {active && <p>操作在后台执行，可以继续阅读或关闭页面；再次进入可查看结果。</p>}
      {operation.status === 'interrupted' && <p>执行器已中断，不会自动重试；已完成内容保留。</p>}
      {operation.errorCode && <p>诊断：{operation.errorCode}</p>}
      <NewsOperationResult operation={operation} />
    </div>}
  </section>;
}

export function NewsOperationResult({ operation }: { operation: NewsOperation }) {
  const result = operation.result;
  if (!result) return null;
  return <>
    {result.sources && <p>新增 {result.sources.reduce((n, item) => n + item.created, 0)} 条 · 重复/更新 {result.sources.reduce((n, item) => n + item.duplicates, 0)} 条 · 来源失败 {result.sources.filter((item) => item.status === 'failed').length} 个</p>}
    {result.items && <p>已增强 {result.enhanced} · 缓存复用 {result.cacheHits} · 原生中文 {result.alreadyChinese} · 未处理 {Math.max(0, operation.itemIds.length - (result.considered ?? 0))} · 未完成 {result.failed}</p>}
    <p>本次模型请求 {result.providerCalls} 次{operation.action === 'enhance' ? ` / 上限 ${operation.requestLimit}` : ''}</p>
    {result.items && <details><summary>逐条处理结果</summary><ul>{result.items.map((item) => <li key={item.contentId}>资讯 #{item.contentId}：{({ enhanced: '已完成', cached: '已复用缓存', already_chinese: '原生中文', failed: '处理失败', budget_exhausted: '额度不足，未完成' } as Record<string, string>)[item.status] ?? '未处理'}{item.materialKind === 'title_only' ? ' · 仅标题，未生成正文摘要' : item.materialKind === 'article_body' ? ' · 依据正文' : item.materialKind === 'feed_summary' ? ' · 依据来源摘要' : ''}</li>)}</ul></details>}
  </>;
}
