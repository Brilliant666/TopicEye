'use client';

import { Activity, AlertTriangle, CheckCircle2, Clock3, Edit3, PauseCircle, RefreshCw, TimerReset } from 'lucide-react';
import { Button, Panel, cx } from '@/components/ui';
import { timeAgo } from '@/lib/utils';
import type { BackendSource } from '@/components/SourceRow';
import {
  formatDateTime,
  formatDuration,
  formatInterval,
  getSyncTiming,
  sourceTypeLabel,
  syncBoardOrder,
  type SourceSyncBoardModel,
  type SyncBoardKey,
} from '@/lib/source-sync-board';

const syncBoardMeta: Record<SyncBoardKey, { label: string; desc: string; tone: string; text: string; border: string; bg: string; bar: string; icon: typeof Clock3 }> = {
  running: { label: '同步中', desc: '正在执行手动或后台采集', tone: 'primary', text: 'text-primary', border: 'border-primary-border', bg: 'bg-primary-light', bar: 'bg-primary', icon: RefreshCw },
  due: { label: '待同步', desc: '已到采集窗口，需要拉取新内容', tone: 'amber', text: 'text-amber', border: 'border-amber-border', bg: 'bg-amber-light', bar: 'bg-amber', icon: TimerReset },
  waiting: { label: '等待同步', desc: '未到下一次采集窗口', tone: 'purple', text: 'text-purple', border: 'border-purple-border', bg: 'bg-purple-light', bar: 'bg-purple', icon: Clock3 },
  fresh: { label: '已同步', desc: '刚完成同步，处于健康窗口', tone: 'teal', text: 'text-teal', border: 'border-teal-border', bg: 'bg-teal-light', bar: 'bg-teal', icon: CheckCircle2 },
  error: { label: '同步异常', desc: '最近一次采集失败或返回错误', tone: 'red', text: 'text-red', border: 'border-red-light', bg: 'bg-red-light', bar: 'bg-red', icon: AlertTriangle },
  paused: { label: '已暂停', desc: '信源已禁用，调度器会跳过', tone: 'neutral', text: 'text-gray-500', border: 'border-gray-200', bg: 'bg-gray-100', bar: 'bg-gray-400', icon: PauseCircle },
};

interface SourceSyncBoardProps {
  syncBoard: SourceSyncBoardModel;
  syncingIds: Set<number>;
  syncResults: Record<number, string>;
  now: Date;
  onEdit: (source: BackendSource) => void;
  onSync: (id: number) => void;
}

function SummaryCard({
  label,
  value,
  helper,
  tone,
  iconClass,
}: {
  label: string;
  value: number;
  helper: string;
  tone: string;
  iconClass: string;
}) {
  return (
    <Panel className="flex justify-between gap-3 p-4">
      <div>
        <div className="mb-2 text-xs text-gray-500">{label}</div>
        <div className="font-mono text-[26px] font-black leading-none text-gray-900">{value}</div>
        <div className="mt-2 text-[11px] text-gray-400">{helper}</div>
      </div>
      <div className={cx('flex h-9 w-9 items-center justify-center rounded-sm', tone, iconClass)}>
        <Activity size={18} strokeWidth={2.2} />
      </div>
    </Panel>
  );
}

export default function SourceSyncBoard({
  syncBoard,
  syncingIds,
  syncResults,
  now,
  onEdit,
  onSync,
}: SourceSyncBoardProps) {
  const nextTiming = syncBoard.nextDueSource ? getSyncTiming(syncBoard.nextDueSource, now) : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="待同步信源" value={syncBoard.dueCount} helper="到达采集窗口" tone="bg-amber-light" iconClass="text-amber" />
        <SummaryCard label="健康运行" value={syncBoard.healthyCount} helper="已同步或等待同步" tone="bg-teal-light" iconClass="text-teal" />
        <SummaryCard label="同步异常" value={syncBoard.errorCount} helper="需要检查错误信息" tone="bg-red-light" iconClass="text-red" />
        <SummaryCard label="已暂停" value={syncBoard.pausedCount} helper="不会进入调度队列" tone="bg-gray-100" iconClass="text-gray-500" />
      </div>

      <Panel className="grid grid-cols-1 gap-4 p-4.5 lg:grid-cols-[minmax(0,1.4fr)_minmax(240px,0.8fr)]">
        <div>
          <h2 className="mb-2 text-[15px] font-black text-gray-800">调度窗口</h2>
          <p className="m-0 text-xs leading-6 text-gray-500">
            看板基于每个信源的最近同步时间与采集频率推导下一次同步状态。后台真实任务队列尚未暴露时，手动触发会临时进入“同步中”，其余状态按当前字段实时计算。
          </p>
        </div>
        <div className="rounded-sm border border-gray-100 bg-gray-50 p-3.5">
          <div className="mb-2 text-xs text-gray-500">下一批优先处理</div>
          {syncBoard.nextDueSource ? (
            <>
              <div className="truncate text-sm font-black text-gray-900">{syncBoard.nextDueSource.name}</div>
              <div className="mt-1.5 text-xs text-gray-500">
                {nextTiming?.diffMinutes !== null && nextTiming?.diffMinutes !== undefined && nextTiming.diffMinutes > 0
                  ? `${formatDuration(nextTiming.diffMinutes)}后到期`
                  : '已到同步窗口'}
              </div>
            </>
          ) : (
            <div className="text-[13px] text-gray-400">暂无待处理信源</div>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {syncBoardOrder.map((key) => {
          const meta = syncBoardMeta[key];
          const Icon = meta.icon;
          const items = syncBoard.columns[key];
          return (
            <Panel key={key} className="min-w-0 overflow-hidden">
              <div className={cx('flex items-center justify-between gap-3 border-b px-3.5 py-3', meta.bg, meta.border)}>
                <div className="flex min-w-0 items-center gap-2">
                  <Icon size={16} strokeWidth={2.2} className={meta.text} />
                  <div className="min-w-0">
                    <h3 className={cx('m-0 text-[13px] font-black', meta.text)}>{meta.label}</h3>
                    <div className="mt-0.5 truncate text-[11px] text-gray-500">{meta.desc}</div>
                  </div>
                </div>
                <span className={cx('font-mono text-xs font-black', meta.text)}>{items.length}</span>
              </div>

              <div className="flex max-h-[clamp(360px,calc(100vh-430px),720px)] flex-col gap-2.5 overflow-y-auto p-2.5">
                {items.map((source) => {
                  const timing = getSyncTiming(source, now);
                  const isDue = timing.diffMinutes === null || timing.diffMinutes <= 0;
                  const result = syncResults[source.id];
                  const disabled = syncingIds.has(source.id) || key === 'paused';
                  return (
                    <article key={source.id} className={cx('rounded-sm border bg-white p-3', source.sync_error ? 'border-red-light' : 'border-gray-200')}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h4 className="m-0 truncate text-[13px] font-black text-gray-800">{source.name}</h4>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">{sourceTypeLabel(source.source_type)}</span>
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">{source.category || '未分类'}</span>
                          </div>
                        </div>
                        <span className={cx('whitespace-nowrap rounded-full border px-2 py-0.5 font-mono text-[10px]', meta.bg, meta.border, meta.text)}>
                          {formatInterval(timing.intervalMinutes)}
                        </span>
                      </div>

                      <div className="mt-2.5">
                        <div className="mb-1 flex justify-between text-[11px] text-gray-500">
                          <span>同步窗口</span>
                          <span>{Math.min(timing.progress, 100)}%</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
                          <div className={cx('h-full rounded-full', key === 'error' ? 'bg-red' : key === 'due' ? 'bg-amber' : meta.bar)} style={{ width: `${Math.max(4, Math.min(timing.progress, 100))}%` }} />
                        </div>
                      </div>

                      <div className="mt-2.5 grid gap-1 text-[11px] leading-5 text-gray-500">
                        <div>上次：{timeAgo(source.last_sync_at)} · {formatDateTime(timing.lastSyncAt)}</div>
                        <div className={isDue ? 'text-amber' : 'text-gray-500'}>
                          下次：{timing.nextSyncAt ? formatDateTime(timing.nextSyncAt) : '立即可同步'}
                          {timing.diffMinutes !== null ? ` · ${isDue ? '已到期' : `${formatDuration(timing.diffMinutes)}后`}` : ''}
                        </div>
                        {source.sync_error && <div className="break-words text-red">{source.sync_error}</div>}
                        {result && <div className={result.startsWith('同步失败') ? 'text-red' : 'text-teal'}>{result}</div>}
                      </div>

                      <div className="mt-3 flex gap-2">
                        <Button
                          type="button"
                          variant={disabled ? 'secondary' : 'success'}
                          onClick={() => onSync(source.id)}
                          disabled={disabled}
                          className="min-h-7 flex-1 px-2 py-1 text-[11px]"
                        >
                          <RefreshCw size={12} strokeWidth={2.2} className={syncingIds.has(source.id) ? 'animate-spin' : ''} />
                          {syncingIds.has(source.id) ? '同步中' : '立即同步'}
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => onEdit(source)} className="min-h-7 px-2.5 py-1 text-[11px]">
                          <Edit3 size={12} strokeWidth={2.1} />
                          编辑
                        </Button>
                      </div>
                    </article>
                  );
                })}
                {items.length === 0 && (
                  <div className="grid min-h-24 place-items-center rounded-sm border border-dashed border-gray-200 bg-gray-50 p-3.5 text-center text-xs text-gray-400">
                    当前没有信源
                  </div>
                )}
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
