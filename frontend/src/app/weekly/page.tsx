'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  FileText,
  Folder,
  Flame,
  Inbox,
  KeyRound,
  Lightbulb,
  Loader2,
  Newspaper,
  Pin,
  RadioTower,
  RefreshCw,
  Smartphone,
  Target,
  TrendingUp,
} from 'lucide-react';
import { Button, Panel, cx } from '@/components/ui';
import { weeklyDigestApi } from '@/lib/api';
import type { WeeklyDigest, WeeklyDigestWeekSummary } from '@/types';
import {
  CurrentPeriodButton,
  PlatformHeading,
  ReportActionButton,
  ReportBadge,
  ReportFooterStat,
  ReportSectionTitle,
  ReportSidebarHeader,
  ReportStatusPanel,
} from '@/components/ReportLayout';

interface TrendItem {
  title: string;
  desc: string;
  color?: string;
  momentum?: string;
}

interface ClusterItem {
  name: string;
  count: number;
  representative_title: string;
  heat: number;
}

interface PickItem {
  title: string;
  reason: string;
  source?: string;
  category?: string;
  platforms: string[];
  score?: number;
}

interface ActionItem {
  title: string;
  angle: string;
  platform?: string;
  difficulty?: string;
}

interface CategoryInfo {
  count: number;
  top_title?: string;
  avg_score?: number;
}

function WeeklyStat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: React.ReactNode;
  tone?: 'primary' | 'teal' | 'amber' | 'neutral';
}) {
  const toneClass = {
    primary: 'border-primary-border bg-primary-light text-primary',
    teal: 'border-teal-border bg-teal-light text-teal',
    amber: 'border-amber-border bg-amber-light text-amber',
    neutral: 'border-gray-200 bg-gray-50 text-gray-900',
  }[tone];

  return (
    <div className={cx('min-w-0 rounded-sm border px-3 py-3', toneClass)}>
      <div className="mb-1.5 text-[11px] text-gray-500">{label}</div>
      <div className="font-mono text-[21px] font-black leading-none">{value}</div>
    </div>
  );
}

function getCurrentWeekKey() {
  const now = new Date();
  const janFirst = new Date(now.getFullYear(), 0, 1);
  const days = Math.floor((now.getTime() - janFirst.getTime()) / 86400000);
  const weekNum = Math.ceil((days + janFirst.getDay() + 1) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

function statusLabel(status: string) {
  if (status === 'DONE') return '已完成';
  if (status === 'ERROR') return '失败';
  if (status === 'GENERATING') return '生成中';
  return '待生成';
}

function statusClass(status: string) {
  if (status === 'DONE') return 'bg-teal-light text-teal';
  if (status === 'ERROR') return 'bg-red-light text-red';
  if (status === 'GENERATING') return 'bg-primary-light text-primary';
  return 'bg-gray-100 text-gray-400';
}

function momentumMeta(momentum?: string) {
  if (momentum === 'up') return { label: '上升', icon: ArrowUp, cls: 'bg-teal-light text-teal' };
  if (momentum === 'down') return { label: '下降', icon: ArrowDown, cls: 'bg-red-light text-red' };
  return { label: '平稳', icon: ArrowRight, cls: 'bg-gray-100 text-gray-500' };
}

function difficultyClass(value?: string) {
  if (value === '简单') return 'bg-teal-light text-teal';
  if (value === '中等') return 'bg-amber-light text-amber';
  return 'bg-red-light text-red';
}

export default function WeeklyDigestPage() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [weeks, setWeeks] = useState<WeeklyDigestWeekSummary[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [weeksLoading, setWeeksLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setWeeksLoading(true);
        const data = await weeklyDigestApi.listWeeks();
        setWeeks(data.weeks || []);
      } finally {
        setWeeksLoading(false);
      }
    })();
  }, []);

  const fetchDigest = useCallback(async (weekKey?: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = weekKey ? await weeklyDigestApi.getByWeek(weekKey) : await weeklyDigestApi.getCurrent();
      setDigest(data);
      setSelectedWeek(data.week_key);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      if (errMsg?.includes('404') || errMsg?.includes('not found')) {
        setDigest(null);
        setError(weekKey ? `${weekKey} 暂无周刊` : '暂无周刊数据');
      } else {
        setError(errMsg || '加载失败');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchDigest();
  }, [fetchDigest]);

  const handleWeekSelect = useCallback((weekKey: string) => {
    if (weekKey === selectedWeek) return;
    fetchDigest(weekKey);
  }, [selectedWeek, fetchDigest]);

  const handleRegenerate = async (weekKey?: string) => {
    try {
      setGenerating(true);
      const data = await weeklyDigestApi.generate(weekKey);
      setDigest(data);
      const weeksData = await weeklyDigestApi.listWeeks();
      setWeeks(weeksData.weeks || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const parseJson = <T,>(val: unknown, fallback: T): T => {
    if (typeof val === 'string') {
      try {
        return JSON.parse(val) as T;
      } catch {
        return fallback;
      }
    }
    return (val as T) ?? fallback;
  };

  const keywords = parseJson<string[]>(digest?.keywords, []);
  const trends = parseJson<TrendItem[]>(digest?.trends, []);
  const topPicks = parseJson<PickItem[]>(digest?.top_picks, []);
  const categorySummary = parseJson<Record<string, CategoryInfo>>(digest?.category_summary, {});
  const platformTips = parseJson<Record<string, string[]>>(digest?.platform_tips, {});
  const topicClusters = parseJson<ClusterItem[]>(digest?.topic_clusters, []);
  const actionItems = parseJson<ActionItem[]>(digest?.action_items, []);
  const isCurrentWeek = digest?.week_key === getCurrentWeekKey();

  const visibleWeeks = useMemo(() => weeks, [weeks]);

  return (
    <div className="flex h-full overflow-hidden">
      <aside className="flex w-[260px] min-w-[260px] flex-col overflow-hidden border-r border-gray-200 bg-white">
        <ReportSidebarHeader icon={ClipboardList} title="历史周刊" countText={`共 ${weeks.length} 期`} />

        <div className="px-3 pb-1 pt-2">
          <CurrentPeriodButton active={isCurrentWeek || !selectedWeek} icon={Pin} onClick={() => fetchDigest()}>
            本周
          </CurrentPeriodButton>
        </div>

        <div className="flex-1 overflow-y-auto px-3 pb-3 pt-1">
          {weeksLoading ? (
            <div className="px-2 py-5 text-center text-xs text-gray-400">加载中...</div>
          ) : visibleWeeks.length === 0 ? (
            <div className="px-2 py-5 text-center text-xs text-gray-400">暂无历史周刊</div>
          ) : (
            visibleWeeks.map((w) => {
              const isActive = selectedWeek === w.week_key;
              return (
                <button
                  key={w.week_key}
                  type="button"
                  onClick={() => handleWeekSelect(w.week_key)}
                  className={cx(
                    'mb-0.5 block w-full rounded-xs border-l-3 px-3 py-2.5 text-left text-[13px] transition',
                    isActive ? 'border-l-primary bg-primary-light font-bold text-gray-900' : 'border-l-transparent text-gray-600 hover:bg-gray-50',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className={isActive ? 'text-gray-900' : 'text-gray-700'}>{w.week_label}</span>
                    <span className={cx('rounded px-1.5 py-0.5 text-[9px] font-bold', statusClass(w.status))}>
                      {statusLabel(w.status)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-gray-400">{w.week_key}</div>
                  {w.takeaway && <div className="mt-1 truncate text-[11px] text-gray-400">{w.takeaway}</div>}
                </button>
              );
            })
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto px-10 py-7 pb-16">
        <header className="mb-4 flex items-start justify-between gap-5">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2.5">
              <h1 className="m-0 text-[26px] font-black text-gray-900">AI 周刊</h1>
              <ReportBadge>WEEKLY REVIEW</ReportBadge>
              {!isCurrentWeek && digest && <ReportBadge tone="history">历史回顾</ReportBadge>}
            </div>
            <p className="m-0 text-[13px] text-gray-500">
              {digest ? `${digest.week_label}（${digest.week_start} ~ ${digest.week_end}）` : '加载中...'}
              {digest?.content_count ? ` · 基于 ${digest.content_count} 条内容分析` : ''}
            </p>
          </div>
          <ReportActionButton onClick={() => handleRegenerate(digest?.week_key)} loading={generating} icon={RefreshCw}>
            重新生成
          </ReportActionButton>
        </header>

        {loading ? (
          <ReportStatusPanel icon={ClipboardList}>正在加载周刊...</ReportStatusPanel>
        ) : error ? (
          <ReportStatusPanel icon={AlertTriangle} tone="error">{error}</ReportStatusPanel>
        ) : digest?.status === 'ERROR' ? (
          <div className="grid min-h-[360px] place-items-center p-10 text-center">
            <div>
              <AlertTriangle size={30} className="mx-auto mb-3 text-red" strokeWidth={1.9} />
              <div className="mb-3 text-sm text-gray-500">{digest.overview}</div>
              <ReportActionButton onClick={() => handleRegenerate(digest.week_key)} loading={generating} icon={RefreshCw}>
                重试生成
              </ReportActionButton>
            </div>
          </div>
        ) : digest?.status === 'GENERATING' || digest?.status === 'PENDING' ? (
          <ReportStatusPanel
            icon={Loader2}
            action={(
              <Button type="button" variant="secondary" onClick={() => fetchDigest(digest.week_key)}>
                刷新状态
              </Button>
            )}
          >
            周刊生成中，请稍候...
          </ReportStatusPanel>
        ) : digest ? (
          <article className="max-w-[900px]">
            <Panel className="relative mb-4.5 overflow-hidden p-6 shadow-[0_18px_48px_rgba(15,23,42,0.06)]">
              <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--color-primary),var(--color-teal))]" />
              <div className="relative grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_132px]">
                <div className="min-w-0">
                  <div className="mb-4 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-primary-border bg-primary-light px-2.5 py-1 font-mono text-[11px] font-black text-primary">
                      TOPIC RADAR WEEKLY
                    </span>
                    <span className="text-xs text-gray-500">{digest.week_label}</span>
                  </div>
                  <h2 className="mb-3.5 text-[34px] font-black leading-none text-gray-900">
                    选题雷达<br />周刊
                  </h2>
                  <p className="max-w-[620px] text-base font-bold leading-7 text-gray-700">
                    {digest.takeaway || digest.overview || '本周内容已完成归档，等待进一步分析。'}
                  </p>
                </div>
                <div className="min-w-[122px] rounded-sm border border-primary-border bg-primary-light px-3.5 py-3 text-right">
                  <div className="mb-1.5 text-[11px] text-gray-500">WEEK</div>
                  <div className="font-mono text-[22px] font-black text-primary">{digest.week_key}</div>
                  <div className="mt-1 text-[11px] text-gray-500">{digest.week_start} ~ {digest.week_end}</div>
                </div>
              </div>
              <div className="relative mt-5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <WeeklyStat label="内容样本" value={digest.content_count || 0} tone="primary" />
                <WeeklyStat label="完成分析" value={digest.analyzed_count || 0} tone="teal" />
                <WeeklyStat label="推荐选题" value={topPicks.length || 0} tone="amber" />
                <WeeklyStat label="信源覆盖" value={digest.source_count || 0} />
              </div>
            </Panel>

            {digest.overview && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={Newspaper} title="本周概述" />
                <p className="text-sm leading-8 text-gray-600">{digest.overview}</p>
              </Panel>
            )}

            {keywords.length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={KeyRound} title="本周关键词" />
                <div className="flex flex-wrap gap-2">
                  {keywords.map((kw, i) => (
                    <span
                      key={`${kw}-${i}`}
                      className={cx(
                        'rounded-full border px-2.5 py-1 text-xs font-bold text-gray-700',
                        i === 0 ? 'border-primary-border bg-primary-light' : 'border-gray-200 bg-gray-50',
                      )}
                    >
                      {kw}
                    </span>
                  ))}
                </div>
              </Panel>
            )}

            {trends.length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={TrendingUp} title="内容趋势" />
                <div className="flex flex-col gap-3">
                  {trends.map((trend, i) => {
                    const meta = momentumMeta(trend.momentum);
                    const MomentumIcon = meta.icon;
                    return (
                      <div key={`${trend.title}-${i}`} className="grid grid-cols-[34px_minmax(0,1fr)_auto] items-start gap-3 border-t border-gray-100 py-3.5 first:border-t-0">
                        <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-primary font-mono text-xs font-black text-white">
                          {String(i + 1).padStart(2, '0')}
                        </div>
                        <div className="min-w-0">
                          <div className="mb-1 text-[15px] font-black text-gray-900">{trend.title}</div>
                          <div className="text-[13px] leading-7 text-gray-500">{trend.desc}</div>
                        </div>
                        {trend.momentum && (
                          <span className={cx('rounded px-2 py-0.5 text-[10px] font-bold', meta.cls)}>
                            <span className="inline-flex items-center gap-1">
                              <MomentumIcon size={12} strokeWidth={2.2} />
                              {meta.label}
                            </span>
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Panel>
            )}

            {topicClusters.length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={Flame} title="热门话题聚类" />
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {topicClusters.map((cluster, i) => (
                    <div
                      key={`${cluster.name}-${i}`}
                      className={cx('rounded-sm border p-4', i === 0 ? 'border-primary-border bg-primary-light' : 'border-gray-200 bg-gray-50')}
                    >
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="truncate text-sm font-black text-gray-900">{cluster.name}</span>
                        <span className={cx('rounded-full border px-2 py-0.5 font-mono text-[11px] font-black', i === 0 ? 'border-primary-border bg-white text-primary' : 'border-teal-border bg-teal-light text-teal')}>
                          {cluster.count}篇
                        </span>
                      </div>
                      <div className="text-xs leading-5 text-gray-500">代表: {cluster.representative_title}</div>
                      <div className="mt-2 flex items-center gap-1.5">
                        <div className="h-1 flex-1 overflow-hidden rounded-full bg-gray-100">
                          <div className="h-full rounded-full bg-[linear-gradient(90deg,var(--color-primary),var(--color-teal))]" style={{ width: `${Math.min(cluster.heat, 100)}%` }} />
                        </div>
                        <span className="font-mono text-[10px] text-gray-400">{cluster.heat}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {topPicks.length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={Target} title="精选选题 TOP 5" />
                <div className="flex flex-col gap-2.5">
                  {topPicks.map((pick, i) => (
                    <div key={`${pick.title}-${i}`} className="grid grid-cols-[32px_minmax(0,1fr)_52px] items-start gap-3 border-t border-gray-100 py-4 first:border-t-0">
                      <div className={cx('flex h-6.5 w-6.5 items-center justify-center rounded-full font-mono text-xs font-black', i === 0 ? 'bg-primary text-white' : i === 1 ? 'bg-amber text-white' : 'bg-gray-100 text-gray-600')}>
                        {i + 1}
                      </div>
                      <div className="min-w-0">
                        <div className="text-[15px] font-black leading-6 text-gray-900">{pick.title}</div>
                        <div className="mt-1 text-xs leading-5 text-gray-500">{pick.reason}</div>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {pick.source && <span className="text-[10px] text-gray-400">信源 {pick.source}</span>}
                          {pick.category && <span className="rounded bg-teal-light px-2 py-0.5 text-[10px] text-teal">{pick.category}</span>}
                          {(pick.platforms ?? []).map((p, j) => (
                            <span key={`${p}-${j}`} className="rounded bg-teal-light px-2 py-0.5 text-[10px] text-teal">{p}</span>
                          ))}
                        </div>
                      </div>
                      {pick.score && <div className="text-right font-mono text-[21px] font-black text-primary">{pick.score}</div>}
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {Object.keys(categorySummary).length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={BarChart3} title="分类概览" />
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {Object.entries(categorySummary).map(([cat, info]) => (
                    <div key={cat} className="rounded-sm border border-gray-200 bg-gray-50 p-4">
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="truncate text-sm font-black text-gray-900">{cat}</span>
                        <span className="font-mono text-xs font-black text-primary">{info.count}篇</span>
                      </div>
                      <div className="truncate text-xs text-gray-500">{info.top_title || '-'}</div>
                      {info.avg_score !== undefined && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <div className="h-1 flex-1 overflow-hidden rounded-full bg-gray-100">
                            <div className="h-full rounded-full bg-teal" style={{ width: `${Math.min(info.avg_score, 100)}%` }} />
                          </div>
                          <span className="font-mono text-[10px] text-gray-400">{info.avg_score.toFixed(0)}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {actionItems.length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={CheckCircle2} title="下周创作行动清单" />
                <div className="flex flex-col gap-2.5">
                  {actionItems.map((item, i) => (
                    <div key={`${item.title}-${i}`} className={cx('flex items-start gap-3 rounded-sm border p-4', i < 3 ? 'border-primary-border bg-primary-light' : 'border-gray-200 bg-gray-50')}>
                      <div className={cx('mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold', i < 3 ? 'bg-primary-light text-primary' : 'bg-gray-100 text-gray-500')}>{i + 1}</div>
                      <div className="flex-1">
                        <div className="mb-1 text-sm font-bold text-gray-900">{item.title}</div>
                        <div className="mb-1.5 text-xs leading-5 text-gray-500">{item.angle}</div>
                        <div className="flex flex-wrap gap-1.5">
                          {item.platform && <span className="rounded bg-teal-light px-2 py-0.5 text-[10px] text-teal">{item.platform}</span>}
                          {item.difficulty && <span className={cx('rounded px-2 py-0.5 text-[10px] font-medium', difficultyClass(item.difficulty))}>{item.difficulty}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {Object.keys(platformTips).length > 0 && (
              <Panel className="mb-4.5 p-5">
                <ReportSectionTitle icon={Lightbulb} title="平台创作建议" />
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {Object.entries(platformTips).map(([platform, tips]) => (
                    <Panel key={platform} className="p-4.5">
                      <PlatformHeading icon={Smartphone} label={platform} />
                      {(Array.isArray(tips) ? tips : []).map((tip, j) => (
                        <div key={`${platform}-${j}`} className={cx('mb-2 border-l-2 pl-2.5 text-xs leading-6 text-gray-500', j === 0 ? 'border-primary-border' : 'border-gray-200')}>
                          {tip}
                        </div>
                      ))}
                    </Panel>
                  ))}
                </div>
              </Panel>
            )}

            <div className="flex flex-wrap gap-6 border-t border-gray-200 pt-3.5 text-xs text-gray-400">
              <ReportFooterStat icon={CalendarDays}>{digest.week_label}</ReportFooterStat>
              <ReportFooterStat icon={BarChart3}>分析 {digest.analyzed_count} 条内容</ReportFooterStat>
              <ReportFooterStat icon={RadioTower}>来自 {digest.source_count} 个信源</ReportFooterStat>
              <ReportFooterStat icon={Folder}>覆盖 {digest.category_count} 个分类</ReportFooterStat>
            </div>
          </article>
        ) : (
          <ReportStatusPanel icon={Inbox}>暂无周刊数据</ReportStatusPanel>
        )}
      </main>
    </div>
  );
}
