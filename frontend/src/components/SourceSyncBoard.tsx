'use client';

import { Activity, AlertTriangle, CheckCircle2, Clock3, Edit3, PauseCircle, RefreshCw, TimerReset } from 'lucide-react';
import { T } from '@/lib/design-tokens';
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

const syncBoardMeta: Record<SyncBoardKey, { label: string; desc: string; color: string; bg: string; border: string; icon: typeof Clock3 }> = {
  running: { label: '同步中', desc: '正在执行手动或后台采集', color: T.primary, bg: T.primaryLight, border: T.primaryBorder, icon: RefreshCw },
  due: { label: '待同步', desc: '已到采集窗口，需要拉取新内容', color: T.amber, bg: T.amberLight, border: T.amberBorder, icon: TimerReset },
  waiting: { label: '等待同步', desc: '未到下一次采集窗口', color: T.purple, bg: T.purpleLight, border: T.purpleBorder, icon: Clock3 },
  fresh: { label: '已同步', desc: '刚完成同步，处于健康窗口', color: T.teal, bg: T.tealLight, border: T.tealBorder, icon: CheckCircle2 },
  error: { label: '同步异常', desc: '最近一次采集失败或返回错误', color: T.red, bg: T.redLight, border: T.redLight, icon: AlertTriangle },
  paused: { label: '已暂停', desc: '信源已禁用，调度器会跳过', color: T.gray500, bg: T.gray100, border: T.gray200, icon: PauseCircle },
};

interface SourceSyncBoardProps {
  syncBoard: SourceSyncBoardModel;
  syncingIds: Set<number>;
  syncResults: Record<number, string>;
  now: Date;
  onEdit: (source: BackendSource) => void;
  onSync: (id: number) => void;
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        {[
          { label: '待同步信源', value: syncBoard.dueCount, helper: '到达采集窗口', color: T.amber, bg: T.amberLight },
          { label: '健康运行', value: syncBoard.healthyCount, helper: '已同步或等待同步', color: T.teal, bg: T.tealLight },
          { label: '同步异常', value: syncBoard.errorCount, helper: '需要检查错误信息', color: T.red, bg: T.redLight },
          { label: '已暂停', value: syncBoard.pausedCount, helper: '不会进入调度队列', color: T.gray500, bg: T.gray100 },
        ].map((item) => (
          <div key={item.label} style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, color: T.gray500, marginBottom: 8 }}>{item.label}</div>
              <div style={{ fontSize: 26, lineHeight: 1, color: T.gray900, fontFamily: T.mono }}>{item.value}</div>
              <div style={{ fontSize: 11, color: T.gray400, marginTop: 8 }}>{item.helper}</div>
            </div>
            <div style={{ width: 36, height: 36, borderRadius: T.radiusSm, background: item.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color: item.color }}>
              <Activity size={18} strokeWidth={2.2} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 18, display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(240px, 0.8fr)', gap: 18 }}>
        <div>
          <h2 style={{ fontSize: 15, color: T.gray800, margin: '0 0 8px' }}>调度窗口</h2>
          <p style={{ margin: 0, fontSize: 12, color: T.gray500, lineHeight: 1.7 }}>
            看板基于每个信源的最近同步时间与采集频率推导下一次同步状态。后台真实任务队列尚未暴露时，手动触发会临时进入“同步中”，其余状态按当前字段实时计算。
          </p>
        </div>
        <div style={{ background: T.gray50, border: `1px solid ${T.gray100}`, borderRadius: T.radiusSm, padding: 14 }}>
          <div style={{ fontSize: 12, color: T.gray500, marginBottom: 8 }}>下一批优先处理</div>
          {syncBoard.nextDueSource ? (
            <>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.gray900, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {syncBoard.nextDueSource.name}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: T.gray500 }}>
                {nextTiming?.diffMinutes !== null && nextTiming?.diffMinutes !== undefined && nextTiming.diffMinutes > 0
                  ? `${formatDuration(nextTiming.diffMinutes)}后到期`
                  : '已到同步窗口'}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 13, color: T.gray400 }}>暂无待处理信源</div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, alignItems: 'start' }}>
        {syncBoardOrder.map((key) => {
          const meta = syncBoardMeta[key];
          const Icon = meta.icon;
          const items = syncBoard.columns[key];
          return (
            <section key={key} style={{ minWidth: 0, background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, overflow: 'hidden' }}>
              <div style={{ padding: '13px 14px', background: meta.bg, borderBottom: `1px solid ${meta.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <Icon size={16} strokeWidth={2.2} color={meta.color} />
                  <div style={{ minWidth: 0 }}>
                    <h3 style={{ margin: 0, fontSize: 13, color: meta.color }}>{meta.label}</h3>
                    <div style={{ fontSize: 11, color: T.gray500, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{meta.desc}</div>
                  </div>
                </div>
                <span style={{ fontSize: 12, fontFamily: T.mono, color: meta.color, fontWeight: 700 }}>{items.length}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 10, maxHeight: 'clamp(360px, calc(100vh - 430px), 720px)', overflowY: 'auto' }}>
                {items.map((source) => {
                  const timing = getSyncTiming(source, now);
                  const isDue = timing.diffMinutes === null || timing.diffMinutes <= 0;
                  const result = syncResults[source.id];
                  return (
                    <article key={source.id} style={{ border: `1px solid ${source.sync_error ? T.redLight : T.gray200}`, borderRadius: T.radiusSm, padding: 12, background: T.white }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                        <div style={{ minWidth: 0 }}>
                          <h4 style={{ margin: 0, fontSize: 13, color: T.gray800, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{source.name}</h4>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 7 }}>
                            <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, padding: '2px 6px', borderRadius: 4 }}>{sourceTypeLabel(source.source_type)}</span>
                            <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, padding: '2px 6px', borderRadius: 4 }}>{source.category || '未分类'}</span>
                          </div>
                        </div>
                        <span style={{ fontSize: 10, fontFamily: T.mono, color: meta.color, background: meta.bg, border: `1px solid ${meta.border}`, borderRadius: 999, padding: '2px 7px', whiteSpace: 'nowrap' }}>
                          {formatInterval(timing.intervalMinutes)}
                        </span>
                      </div>

                      <div style={{ marginTop: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.gray500, marginBottom: 5 }}>
                          <span>同步窗口</span>
                          <span>{Math.min(timing.progress, 100)}%</span>
                        </div>
                        <div style={{ height: 6, background: T.gray100, borderRadius: 999, overflow: 'hidden' }}>
                          <div style={{ width: `${Math.max(4, Math.min(timing.progress, 100))}%`, height: '100%', background: key === 'error' ? T.red : key === 'due' ? T.amber : meta.color, borderRadius: 999 }} />
                        </div>
                      </div>

                      <div style={{ marginTop: 10, display: 'grid', gap: 4, fontSize: 11, color: T.gray500, lineHeight: 1.45 }}>
                        <div>上次：{timeAgo(source.last_sync_at)} · {formatDateTime(timing.lastSyncAt)}</div>
                        <div style={{ color: isDue ? T.amber : T.gray500 }}>
                          下次：{timing.nextSyncAt ? formatDateTime(timing.nextSyncAt) : '立即可同步'}
                          {timing.diffMinutes !== null ? ` · ${isDue ? '已到期' : `${formatDuration(timing.diffMinutes)}后`}` : ''}
                        </div>
                        {source.sync_error && <div style={{ color: T.red, wordBreak: 'break-word' }}>{source.sync_error}</div>}
                        {result && <div style={{ color: result.startsWith('同步失败') ? T.red : T.teal }}>{result}</div>}
                      </div>

                      <div style={{ display: 'flex', gap: 7, marginTop: 11 }}>
                        <button
                          onClick={() => onSync(source.id)}
                          disabled={syncingIds.has(source.id) || key === 'paused'}
                          style={{ flex: 1, minHeight: 30, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px 8px', border: `1px solid ${syncingIds.has(source.id) || key === 'paused' ? T.gray200 : T.tealBorder}`, borderRadius: T.radiusXs, background: syncingIds.has(source.id) || key === 'paused' ? T.gray100 : T.tealLight, color: syncingIds.has(source.id) || key === 'paused' ? T.gray400 : T.teal, fontSize: 11, fontWeight: 700, cursor: syncingIds.has(source.id) ? 'wait' : key === 'paused' ? 'not-allowed' : 'pointer' }}
                        >
                          <RefreshCw size={12} strokeWidth={2.2} />
                          {syncingIds.has(source.id) ? '同步中' : '立即同步'}
                        </button>
                        <button
                          onClick={() => onEdit(source)}
                          style={{ minHeight: 30, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px 9px', border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, background: T.white, color: T.gray600, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
                        >
                          <Edit3 size={12} strokeWidth={2.1} />
                          编辑
                        </button>
                      </div>
                    </article>
                  );
                })}
                {items.length === 0 && (
                  <div style={{ minHeight: 96, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: T.gray400, fontSize: 12, background: T.gray50, border: `1px dashed ${T.gray200}`, borderRadius: T.radiusSm, padding: 14 }}>
                    当前没有信源
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
