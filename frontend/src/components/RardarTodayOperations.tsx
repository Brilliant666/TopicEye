'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthContext } from '@/providers/AppProvider';
import { todayOperationsApi, todayOperationLabel, type TodayOperation } from '@/lib/api/today-operations';
import styles from './RardarNewsOperations.module.css';
import { beijingTime } from '@/lib/rardar-trending';

type BoardContext = { syncedAt: string | null; checkedAt?: string | null; context?: 'dual_board' | 'exact_explosion' };

export default function RardarTodayOperations({ syncedAt, checkedAt, context = 'exact_explosion' }: BoardContext) {
  const { currentUser, authLoading } = useAuthContext();
  if (authLoading) return null;
  if (!currentUser) return <p className={styles.login}><Link href="/login">管理员登录</Link>后可检查并同步榜单</p>;
  if (currentUser.role !== 'admin') return null;
  return <AdminTodayOperations syncedAt={syncedAt} checkedAt={checkedAt} context={context} userId={currentUser.id} key={currentUser.id} />;
}

function AdminTodayOperations({ syncedAt, checkedAt, context, userId }: BoardContext & { userId: number }) {
  const router = useRouter();
  const [operation, setOperation] = useState<TodayOperation | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [sending, setSending] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const lastOperation = useRef<TodayOperation | null>(null);
  const refreshed = useRef<string | null>(null);
  const storageKey = `rardar-today-pending-${userId}`;
  const active = operation?.status === 'running';

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const saved = sessionStorage.getItem(storageKey);
        if (saved && /^[0-9a-f-]{36}$/i.test(saved)) setPendingId(saved);
        const state = await todayOperationsApi.current();
        if (cancelled) return;
        const previous = lastOperation.current;
        const candidate = state.latest;
        const next = context !== 'dual_board' || !candidate || isDualBoardOperation(candidate) ? candidate : null;
        if (previous?.id === next?.id && previous?.status === 'running' && next?.status !== 'running' && refreshed.current !== next?.id) {
          refreshed.current = next?.id ?? null;
          router.refresh();
        }
        lastOperation.current = next;
        setOperation(next);
        setLastSync(state.lastSuccessfulSyncAt ?? null);
        setReady(true);
        setError('');
      } catch {
        if (!cancelled) setError('暂时无法读取检查状态，当前榜单仍可阅读。');
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [router, storageKey, syncedAt, context]);

  async function start() {
    if (inFlight.current || active || !ready) return;
    inFlight.current = true;
    setSending(true);
    setError('');
    const requestId = pendingId ?? crypto.randomUUID();
    setPendingId(requestId);
    try {
      // Persist only retry identity; reloads and GETs never submit automatically.
      sessionStorage.setItem(storageKey, requestId);
      const next = await todayOperationsApi.start(requestId);
      sessionStorage.removeItem(storageKey);
      setPendingId(null);
      lastOperation.current = next;
      setOperation(next);
      if (next.status !== 'running' && refreshed.current !== next.id) {
        refreshed.current = next.id;
        router.refresh();
      }
    } catch {
      setError('提交结果暂未确认；再次点击会确认同一次操作，不会重复启动同步。');
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  return <section className={styles.panel} aria-label="管理员榜单更新">
    <div className={styles.heading}>
      <div><h2>榜单更新</h2><p>读取 GitHub Trending 与 Trendshift 公开日榜 · 不调用模型</p></div>
      <div className={styles.actions}><button type="button" disabled={!ready || sending || active} onClick={() => void start()}>
        {pendingId && !sending ? '确认上次同步结果' : '检查并同步榜单'}
      </button></div>
    </div>
    {context === 'dual_board' ? <p>当前清单发布：{timeLabel(syncedAt)} · 最近来源检查：{timeLabel(checkedAt ?? null)}</p> : <p>当前榜单同步：{timeLabel(syncedAt)}</p>}
    <p>最近成功手动同步：{timeLabel(lastSync)} · 最近手动操作：{timeLabel(operation?.completedAt ?? operation?.startedAt ?? null)}</p>
    {error && <p role="alert">{error}</p>}
    {operation && <TodayOperationResult operation={operation} context={context} />}
  </section>;
}

function timeLabel(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return '暂无记录';
  return beijingTime(value);
}

export function isDualBoardOperation(operation: TodayOperation) {
  return operation.scope === 'dual_board' || operation.result?.generationId?.startsWith('boards-') === true;
}

export function TodayOperationResult({ operation, context = 'exact_explosion' }: { operation: TodayOperation; context?: BoardContext['context'] }) {
  if (context === 'dual_board' && !isDualBoardOperation(operation)) return null;
  return <div className={styles.result} aria-live="polite">
    <strong>{todayOperationLabel(operation.status)}</strong>
    {operation.status === 'running' && <p>可以继续阅读；刷新页面后仍可查看结果，旧有效榜单会保留到验证通过。</p>}
    {['failed', 'interrupted', 'not_configured'].includes(operation.status) && <p>当前有效榜单保留，未自动重试。请检查已有只读同步配置或稍后重试。</p>}
    {operation.status === 'no_complete_board' && <p>来源尚无可替换的有效榜单，当前已保存内容保留。</p>}
    {operation.status === 'partial' && <p>部分来源暂不可用，已取得的新内容和其他健康来源继续保留。</p>}
    {context !== 'dual_board' && operation.result?.window && <p>历史来源观察窗口（北京时间）：{timeLabel(operation.result.window.startedAt)} → {timeLabel(operation.result.window.endedAt)}</p>}
  </div>;
}
