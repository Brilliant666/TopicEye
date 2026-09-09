'use client';

import { useCallback, useEffect, useState } from 'react';
import { request } from '@/lib/api/_core';
import { Button, Panel } from '@/components/ui';

type Budget = { configuredLimit: number | null; attempted: number; remaining: number; day: string; dailyStatus?: { status: string | null; modules: Record<string, Record<string, string | number | null>> } };
type Job = { job_key: string; enabled: boolean; last_status: string | null };
type Log = { id: number; status: string; started_at: string; result_summary: string | null };

export default function RardarDailyOperations() {
  const [budget, setBudget] = useState<Budget | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [limit, setLimit] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    const [usage, jobs, history] = await Promise.all([
      request<Budget>('/scheduler/rardar-daily-config'),
      request<{ jobs: Job[] }>('/scheduler/jobs'),
      request<{ logs: Log[] }>('/scheduler/logs?job_key=rardar_daily_operations&limit=5'),
    ]);
    setBudget(usage);
    setJob(jobs.jobs.find((item) => item.job_key === 'rardar_daily_operations') ?? null);
    setLogs(history.logs);
  }, []);
  useEffect(() => {
    const refresh = () => { void load().catch(() => setNotice('日程状态读取失败，请稍后刷新')); };
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => clearInterval(timer);
  }, [load]);
  const act = async (action: 'pause' | 'resume' | 'run' | 'budget') => {
    setBusy(true);
    try {
      const result = await request<{ status?: string }>(
        action === 'budget' ? '/scheduler/rardar-daily-config' : `/scheduler/jobs/rardar_daily_operations/${action}`,
        { method: 'POST', ...(action === 'budget' ? { body: JSON.stringify({ providerRequestLimit: Number(limit) }) } : {}) },
      );
      setNotice(action === 'budget' ? '额度已保存；当日已登记额度不会自动增加。' : `操作状态：${result.status}`);
      await load();
    } catch {
      setNotice('操作未完成，请查看日程记录或确认运行配置。');
    } finally {
      setBusy(false);
    }
  };
  return <Panel role="region" aria-label="Rardar 每日自动更新" className="mb-6 space-y-3 p-6">
    <h2 className="text-base font-bold">Rardar 每日自动更新</h2>
    <p className="text-sm">上海时间每日 08:30 开始，每小时检查有界续接。由本地 Backend 执行，电脑休眠或进程退出期间不运行；启动后检查补跑。</p>
    <p className="text-sm">{job ? (job.enabled ? '日程已启用' : '日程已暂停') : '日程尚未登记'} · 最近状态：{job?.last_status ?? '未执行'}</p>
    <p className="text-sm">{budget?.day} 每日请求上限：{budget?.configuredLimit ?? '未配置（仅零模型同步）'}；已请求 {budget?.attempted ?? 0}，剩余 {budget?.remaining ?? 0}。</p>
    <div className="flex flex-wrap gap-2">
      <Button disabled={busy || job?.last_status === 'RUNNING'} onClick={() => void act('run')}>立即检查 / 补跑</Button>
      <Button disabled={busy} onClick={() => void act(job?.enabled ? 'pause' : 'resume')}>{job?.enabled ? '暂停日程' : '恢复日程'}</Button>
      <Button disabled={busy} onClick={() => void load().catch(() => setNotice('状态读取失败'))}>刷新状态</Button>
    </div>
    <div className="flex flex-wrap items-center gap-2">
      <label>每日模型请求上限 <input aria-label="每日模型请求上限" className="w-28 rounded border p-2" type="number" min="1" max="100000" value={limit} placeholder={String(budget?.configuredLimit ?? '')} onChange={(event) => setLimit(event.target.value)} /></label>
      <Button disabled={busy || !limit} onClick={() => void act('budget')}>保存费用上限</Button>
    </div>
    <p className="text-xs text-gray-500">同日自动任务、重试及手动操作共享额度；保存更高额度不会给当天运行重新充值。暂停阻止后续日程，当前运行可继续完成。</p>
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {budget?.dailyStatus?.modules && <ul className="space-y-1 text-sm" aria-label="模块处理结果">{Object.entries(budget.dailyStatus.modules).map(([name, result]) => <li key={name}>{name}：{Object.entries(result).map(([key, value]) => `${key}=${value ?? '未知'}`).join(' · ')}</li>)}</ul>}
    <ul className="space-y-2 text-sm">{logs.map((log) => <li key={log.id}><details><summary>{new Date(log.started_at).toLocaleString()} · {log.status}</summary><pre className="whitespace-pre-wrap break-all text-xs">{log.result_summary || '暂无结果；触发并不等于已发布'}</pre></details></li>)}</ul>
  </Panel>;
}
