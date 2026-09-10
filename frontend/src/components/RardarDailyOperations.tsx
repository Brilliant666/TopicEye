'use client';

import { useCallback, useEffect, useState } from 'react';
import { request } from '@/lib/api/_core';
import { Button, Panel } from '@/components/ui';

type Metrics = Record<string, string | number | null>;
export type DailyBudgetView = { configuredLimit: number | null; attempted: number; remaining: number; day: string; interactiveReserve?: number; earlyBackgroundLimit?: number; backgroundRemaining?: number; stageBreakdown?: Record<string, number>; dailyStatus?: { status: string | null; scheduling?: Metrics; modules: Record<string, Metrics> } };
const LABELS: Record<string, string> = { today: 'Today 事实同步', news_refresh: 'News 来源刷新', news_enhance: 'News 中文阅读', discover: 'Discover 精选', public_projects: '公共事实', find_public_materials: '公共项目资料', today_profiles: 'Today 资料', checked: '已检查', processed: '已处理', completed: '已完成', updated: '已更新', cached: '缓存复用', reused: '复用', failed: '失败', unfinished: '待完成', currentPending: '当前内容待处理', historyPending: '历史积压', workSlices: '执行切片', newlyPublishedTotal: '本轮新发布', currentPublishedCount: '当前展示', currentGenerationId: '当前展示版本', currentPublishedAt: '当前展示发布时间', attemptGenerationId: '最新尝试版本', attemptedAt: '最新尝试时间', project_profile: '项目画像', profile_translation: '项目翻译', news_quickread: '资讯中文阅读', scope_value: '价值判断', user_copy: '精选文案', find_project: 'Find 比较' };
const STATUS: Record<string, string> = { completed: '已完成', partial: '部分完成', running: '运行中', pending: '待处理', failed: '失败', interrupted: '已中断', skipped: '已跳过', checked: '已检查', paused: '已暂停', waiting: '等待续接' };
const WAIT: Record<string, string> = { slice_budget_exhausted: '本切片额度已用完，等待轮转', provider_slice_exhausted: '本切片额度已用完，等待轮转', interactive_reserve: '为手动操作保留额度', provider_daily_interactive_reserve: '为手动操作保留额度', early_background_limit: '08:30 前后台额度已用完', provider_daily_early_limit: '08:30 前后台额度已用完', daily_budget_exhausted: '今日额度已用完', calendar_day_changed: '日期已切换，等待下一日程', source_unavailable: '事实来源暂不可用', daily_budget_not_configured: '尚未配置费用上限' };
Object.assign(WAIT, { work_slice_exhausted: '本轮处理时间片已完成，等待续跑', interactive_budget_reserved: '已保留交互请求额度', pre_window_background_limit: '08:30 前后台额度已达到上限', interactive_request_waiting: '优先处理用户检索', provider_request_busy: '等待当前模型请求完成', next_scheduled_pass: '等待下一次日程续跑', administrator_paused: '管理员已暂停，等待恢复' });

export function DailyExecutionSummary({ budget }: { budget: DailyBudgetView }) {
  const scheduling = budget.dailyStatus?.scheduling;
  return <div className="space-y-3 text-sm">
    <p>手动请求保留：{budget.interactiveReserve ?? '未知'} · 08:30 前后台上限：{budget.earlyBackgroundLimit ?? '未知'} · 后台剩余：{budget.backgroundRemaining ?? '未知'}</p>
    {scheduling && <p>执行切片：{scheduling.workSlices ?? 0} · 每切片请求上限：{scheduling.sliceRequestLimit ?? '未知'}{scheduling.waitReason ? ` · ${WAIT[String(scheduling.waitReason)] ?? `等待：${scheduling.waitReason}`}` : ''}</p>}
    {budget.stageBreakdown && <p aria-label="当日请求预留分布">当日请求预留分布：{Object.entries(budget.stageBreakdown).filter(([, count]) => count > 0).map(([stage, count]) => `${LABELS[stage] ?? stage} ${count}`).join(' · ') || '尚无预留'}（包含出站前的保守预记，不等同于费用账单）</p>}
    {budget.dailyStatus?.modules && <ul className="space-y-3" aria-label="模块处理结果">{Object.entries(budget.dailyStatus.modules).map(([name, result]) => <li key={name} className="break-words rounded border p-3"><strong>{LABELS[name] ?? name} · {STATUS[String(result.status)] ?? result.status ?? '未知'}</strong><p>{Object.entries(result).filter(([key]) => key !== 'status' && key !== 'waitReason').map(([key, value]) => `${LABELS[key] ?? key}：${value ?? '未知'}`).join(' · ')}</p>{result.waitReason && <p>{WAIT[String(result.waitReason)] ?? `等待：${result.waitReason}`}</p>}</li>)}</ul>}
    <p className="text-xs text-gray-500">检查、处理与发布分别计数；失败尝试不修改当前展示的版本和发布时间。</p>
  </div>;
}
type Job = { job_key: string; enabled: boolean; last_status: string | null };
type Log = { id: number; status: string; started_at: string; result_summary: string | null };

export default function RardarDailyOperations() {
  const [budget, setBudget] = useState<DailyBudgetView | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<Log[]>([]);
  const [limit, setLimit] = useState('');
  const [reserve, setReserve] = useState('');
  const [early, setEarly] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    const [usage, jobs, history] = await Promise.all([
      request<DailyBudgetView>('/scheduler/rardar-daily-config'),
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
        { method: 'POST', ...(action === 'budget' ? { body: JSON.stringify({ providerRequestLimit: Number(limit || budget?.configuredLimit), ...(reserve !== '' ? { interactiveReserve: Number(reserve) } : {}), ...(early !== '' ? { earlyBackgroundLimit: Number(early) } : {}) }) } : {}) },
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
      <label>手动请求保留 <input aria-label="手动请求保留" className="w-24 rounded border p-2" type="number" min="0" value={reserve} placeholder={String(budget?.interactiveReserve ?? '')} onChange={(event) => setReserve(event.target.value)} /></label>
      <label>08:30 前后台上限 <input aria-label="08:30 前后台上限" className="w-24 rounded border p-2" type="number" min="0" value={early} placeholder={String(budget?.earlyBackgroundLimit ?? '')} onChange={(event) => setEarly(event.target.value)} /></label>
      <Button disabled={busy || (!limit && !reserve && !early)} onClick={() => void act('budget')}>保存费用上限</Button>
    </div>
    <p className="text-xs text-gray-500">同日自动任务、重试及手动操作共享额度；保存更高额度不会给当天运行重新充值。暂停阻止后续工作切片，正在执行的请求可以完成。</p>
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {budget && <DailyExecutionSummary budget={budget} />}
    <ul className="space-y-2 text-sm">{logs.map((log) => <li key={log.id}><details><summary>{new Date(log.started_at).toLocaleString()} · {log.status}</summary><pre className="whitespace-pre-wrap break-all text-xs">{log.result_summary || '暂无结果；触发并不等于已发布'}</pre></details></li>)}</ul>
  </Panel>;
}
