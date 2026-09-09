'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthContext } from '@/providers/AppProvider';
import { todayOperationsApi, todayOperationLabel, type TodayOperation } from '@/lib/api/today-operations';
import styles from './RardarNewsOperations.module.css';

export default function RardarTodayOperations({ syncedAt }: { syncedAt: string | null }) {
  const { currentUser, authLoading } = useAuthContext();
  if (authLoading) return null;
  if (!currentUser) return <p className={styles.login}><Link href="/login">管理员登录</Link>后可检查并同步榜单</p>;
  if (currentUser.role !== 'admin') return null;
  return <AdminTodayOperations syncedAt={syncedAt} userId={currentUser.id} key={currentUser.id} />;
}

function AdminTodayOperations({ syncedAt, userId }: { syncedAt: string | null; userId: number }) {
  const router = useRouter();
  const [operation, setOperation] = useState<TodayOperation | null>(null);
  const [lastSync, setLastSync] = useState(syncedAt);
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
        const next = state.latest;
        if (previous?.id === next?.id && previous?.status === 'running' && next?.status !== 'running' && refreshed.current !== next?.id) {
          refreshed.current = next?.id ?? null;
          router.refresh();
        }
        lastOperation.current = next;
        setOperation(next);
        setLastSync(state.lastSuccessfulSyncAt ?? syncedAt);
        setReady(true);
        setError('');
      } catch {
        if (!cancelled) setError('暂时无法读取检查状态，当前榜单仍可阅读。');
      }
      if (!cancelled) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [router, storageKey, syncedAt]);

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
      <div><h2>榜单更新</h2><p>检查上游已发布的完整 24h 榜单 · 不调用模型，不触发上游采集</p></div>
      <div className={styles.actions}><button type="button" disabled={!ready || sending || active} onClick={() => void start()}>
        {pendingId && !sending ? '确认上次同步结果' : '检查并同步榜单'}
      </button></div>
    </div>
    <p>最近成功同步：{timeLabel(lastSync)} · 最近检查：{timeLabel(operation?.completedAt ?? operation?.startedAt ?? null)}</p>
    {error && <p role="alert">{error}</p>}
    {operation && <TodayOperationResult operation={operation} />}
  </section>;
}

function timeLabel(value: string | null): string {
  if (!value || !Number.isFinite(Date.parse(value))) return '暂无记录';
  return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
}

export function TodayOperationResult({ operation }: { operation: TodayOperation }) {
  return <div className={styles.result} aria-live="polite">
    <strong>{todayOperationLabel(operation.status)}</strong>
    {operation.status === 'running' && <p>可以继续阅读；刷新页面后仍可查看结果，旧有效榜单会保留到验证通过。</p>}
    {['failed', 'interrupted', 'not_configured'].includes(operation.status) && <p>当前有效榜单保留，未自动重试。请检查已有只读同步配置或稍后重试。</p>}
    {operation.status === 'no_complete_board' && <p>上游尚无可替换的完整 24h 榜单，当前榜单和观察窗口不变。</p>}
    {operation.result?.window && <p>来源观察窗口（北京时间）：{timeLabel(operation.result.window.startedAt)} → {timeLabel(operation.result.window.endedAt)}</p>}
  </div>;
}
