'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Circle,
  ExternalLink,
  FileText,
  Inbox,
  KeyRound,
  Lightbulb,
  Loader2,
  Newspaper,
  Pin,
  RefreshCw,
  RotateCcw,
  Smartphone,
  Target,
  TrendingUp,
} from 'lucide-react';
import { Panel, cx } from '@/components/ui';
import { dailyReportApi } from '@/lib/api';
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

interface DailyReportData {
  id: number;
  report_date: string;
  weekday: string;
  edition?: string;
  generated_at?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  cutoff_at?: string | null;
  source_scope?: string;
  source_item_ids?: number[] | null;
  updated_at?: string | null;
  overview: string | null;
  takeaway: string | null;
  keywords: string[] | null;
  trends: Array<{ title: string; desc: string; color: string }> | null;
  top_picks: Array<{ title: string; reason: string; score: number; platforms: string[]; source_url?: string }> | null;
  platform_tips: Record<string, string[]> | null;
  topic_count: number;
  content_count: number;
  analyzed_count: number;
  status: string;
}

interface DateSummary {
  report_date: string;
  weekday: string;
  takeaway: string | null;
  status: string;
  edition?: string;
  generated_at?: string | null;
  cutoff_at?: string | null;
}

interface CalendarDay {
  report_date: string;
  weekday: string;
  status: string;
  edition: string | null;
  generated_at: string | null;
  cutoff_at: string | null;
  takeaway: string | null;
  content_count: number;
  analyzed_count: number;
  topic_count: number;
  has_report: boolean;
  can_generate: boolean;
  is_today: boolean;
}

const EDITION_LABELS: Record<string, string> = {
  noon: '午间快照',
  evening: '晚间快照',
  snapshot: '实时快照',
  manual: '手动快照',
  final: '完整复盘',
  legacy: '历史日报',
};

const CALENDAR_STATUS_META: Record<string, { label: string; text: string; bg: string; border: string; active: string }> = {
  DONE: { label: '已完成', text: 'text-teal', bg: 'bg-teal-light', border: 'border-teal-border', active: 'bg-teal text-white border-teal' },
  ERROR: { label: '失败', text: 'text-red', bg: 'bg-red-light', border: 'border-red-light', active: 'bg-red text-white border-red' },
  MISSING: { label: '缺失', text: 'text-amber', bg: 'bg-amber-light', border: 'border-amber-border', active: 'bg-amber text-white border-amber' },
  GENERATING: { label: '生成中', text: 'text-primary', bg: 'bg-primary-light', border: 'border-primary-border', active: 'bg-primary text-white border-primary' },
};

function localDateString(date = new Date()) {
  return date.toLocaleDateString('en-CA');
}

function formatDateTime(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace('T', ' ');
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatTimeOnly(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(11, 16);
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function parseJson(val: unknown) {
  if (typeof val === 'string') {
    try {
      return JSON.parse(val);
    } catch {
      return null;
    }
  }
  return val;
}

function StatBox({ label, value, tone = 'neutral' }: { label: string; value: React.ReactNode; tone?: 'primary' | 'red' | 'neutral' }) {
  return (
    <div className={cx(
      'rounded-sm border px-3 py-2.5',
      tone === 'primary' && 'border-primary-border bg-primary-light',
      tone === 'red' && 'border-red-light bg-red-light',
      tone === 'neutral' && 'border-gray-200 bg-gray-50',
    )}>
      <div className="mb-1 text-[10px] text-gray-500">{label}</div>
      <div className={cx(
        'font-mono text-xl font-black',
        tone === 'primary' && 'text-primary',
        tone === 'red' && 'text-red',
        tone === 'neutral' && 'text-gray-900',
      )}>
        {value}
      </div>
    </div>
  );
}

export default function DailyReportPage() {
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [dates, setDates] = useState<DateSummary[]>([]);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarStats, setCalendarStats] = useState({ done: 0, error: 0, missing: 0, generating: 0 });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [datesLoading, setDatesLoading] = useState(true);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingDate, setGeneratingDate] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshReportIndexes = useCallback(async () => {
    const [datesData, calendarData] = await Promise.all([
      dailyReportApi.listDates(),
      dailyReportApi.calendar(30),
    ]);
    setDates(datesData.dates || []);
    setCalendarDays(calendarData.days || []);
    setCalendarStats({
      done: calendarData.done_count || 0,
      error: calendarData.error_count || 0,
      missing: calendarData.missing_count || 0,
      generating: calendarData.generating_count || 0,
    });
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setDatesLoading(true);
        setCalendarLoading(true);
        await refreshReportIndexes();
      } finally {
        setDatesLoading(false);
        setCalendarLoading(false);
      }
    })();
  }, [refreshReportIndexes]);

  const fetchReport = useCallback(async (date?: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = date
        ? await dailyReportApi.getByDate(date) as unknown as DailyReportData
        : await dailyReportApi.getToday() as unknown as DailyReportData;
      setReport(data);
      setSelectedDate(data.report_date);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : '加载失败';
      if (errMsg.includes('404') || errMsg.includes('not found')) {
        setReport(null);
        if (date) setSelectedDate(date);
        setError(date ? `${date} 暂无日报` : '暂无日报数据');
      } else {
        setError(errMsg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handleDateSelect = useCallback((date: string) => {
    if (date === selectedDate) return;
    fetchReport(date);
  }, [selectedDate, fetchReport]);

  const generateForDate = useCallback(async (date: string) => {
    try {
      setGenerating(true);
      setGeneratingDate(date);
      setError(null);
      const today = localDateString();
      const data = await dailyReportApi.generateVersion({
        target_date: date,
        edition: date < today ? 'final' : 'manual',
        force: true,
      });
      setReport(data as unknown as DailyReportData);
      setSelectedDate((data as unknown as DailyReportData).report_date || date);
      await refreshReportIndexes();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
      setGeneratingDate(null);
    }
  }, [refreshReportIndexes]);

  const handleRegenerate = async () => {
    await generateForDate(report?.report_date || selectedDate || localDateString());
  };

  const handleCalendarDayClick = (day: CalendarDay) => {
    setSelectedDate(day.report_date);
    if (day.has_report) {
      fetchReport(day.report_date);
      return;
    }
    setReport(null);
    setError(`${day.report_date} 暂无日报，可手动补生成`);
  };

  const keywords = parseJson(report?.keywords);
  const trends = parseJson(report?.trends);
  const topPicks = parseJson(report?.top_picks);
  const platformTips = parseJson(report?.platform_tips);

  const todayStr = localDateString();
  const isToday = report?.report_date === todayStr;
  const editionLabel = EDITION_LABELS[report?.edition || 'snapshot'] || report?.edition || '快照';
  const generatedAt = formatDateTime(report?.generated_at || report?.updated_at);
  const windowText = report?.window_start && report?.window_end
    ? `${formatTimeOnly(report.window_start)} - ${formatTimeOnly(report.window_end)}`
    : '';
  const keywordList = Array.isArray(keywords) ? keywords as string[] : [];
  const trendList = Array.isArray(trends) ? trends as Array<{ title: string; desc: string; color?: string }> : [];
  const pickList = Array.isArray(topPicks)
    ? topPicks as Array<{ title: string; reason: string; score?: number; platforms?: string[]; source_url?: string }>
    : [];
  const leadPick = pickList[0];
  const secondaryPicks = pickList.slice(1);
  const platformTipEntries = platformTips && typeof platformTips === 'object'
    ? Object.entries(platformTips as Record<string, unknown>)
    : [];
  const selectedCalendarDay = calendarDays.find((day) => day.report_date === selectedDate);
  const recoveryDays = calendarDays.filter((day) => day.status === 'MISSING' || day.status === 'ERROR');
  const nextRecoveryDay = recoveryDays[0];
  const recoveryDate = report?.report_date || selectedDate || todayStr;
  const displayDate = report?.report_date || selectedDate;
  const displayWeekday = report?.weekday || selectedCalendarDay?.weekday || '';
  const displayMeta = selectedCalendarDay
    ? CALENDAR_STATUS_META[selectedCalendarDay.status] || CALENDAR_STATUS_META.MISSING
    : null;
  const mainActionLabel = recoveryDate < todayStr ? `补生成 ${recoveryDate}` : `生成 ${recoveryDate}`;

  const generatedDates = useMemo(() => dates.filter((d) => d.report_date !== todayStr), [dates, todayStr]);

  return (
    <div className="h-full w-full overflow-x-auto overflow-y-hidden">
      <div className="flex h-full min-w-[1040px] overflow-hidden">
        <aside className="flex w-[260px] min-w-[260px] flex-col overflow-hidden border-r border-gray-200 bg-[linear-gradient(180deg,#F8FAFC_0%,#FFFFFF_34%,#F8FAFC_100%)]">
          <ReportSidebarHeader icon={CalendarDays} title="日报补录中心" countText={`近 30 天 · 待处理 ${recoveryDays.length}`} />

          <div className="px-3 pb-1 pt-2">
            <CurrentPeriodButton active={selectedDate === todayStr || !selectedDate} icon={Pin} onClick={() => fetchReport()}>
              今天
            </CurrentPeriodButton>
          </div>

          <Panel className="mx-3 my-2 p-3 shadow-[0_8px_22px_rgba(15,23,42,0.04)]">
            <div className="mb-2.5 flex items-center justify-between">
              <div>
                <div className="text-xs font-black text-gray-800">待补录任务</div>
                <div className="mt-0.5 text-[11px] text-gray-400">
                  {nextRecoveryDay ? `下一天 ${nextRecoveryDay.report_date}` : '近 30 天已闭环'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => refreshReportIndexes()}
                title="刷新时间地图"
                className="grid h-6.5 w-6.5 place-items-center rounded-xs border border-gray-200 bg-gray-50 text-gray-500"
              >
                <RefreshCw size={13} />
              </button>
            </div>

            <div className="mb-2.5 grid grid-cols-2 gap-2">
              <StatBox label="缺失日报" value={calendarStats.missing} tone="primary" />
              <StatBox label="生成失败" value={calendarStats.error} tone="red" />
            </div>

            {nextRecoveryDay ? (
              <button
                type="button"
                disabled={generating}
                onClick={() => generateForDate(nextRecoveryDay.report_date)}
                className="mb-3 flex w-full items-center justify-between gap-2 rounded-sm border border-primary-border bg-primary px-3 py-2.5 text-left text-white disabled:cursor-wait disabled:opacity-70"
              >
                <span className="min-w-0">
                  <span className="block text-xs font-black">补生成最近遗漏</span>
                  <span className="mt-0.5 block text-[11px] opacity-80">{nextRecoveryDay.report_date} {nextRecoveryDay.weekday}</span>
                </span>
                {generatingDate === nextRecoveryDay.report_date ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
              </button>
            ) : (
              <div className="mb-3 rounded-sm border border-teal-border bg-teal-light px-3 py-2.5 text-xs font-black text-teal">
                最近 30 天无需补录
              </div>
            )}

            {recoveryDays.length > 0 && (
              <div className="mb-3">
                <div className="mb-1.5 text-[11px] font-black text-gray-500">待补录队列</div>
                <div className="grid gap-1.5">
                  {recoveryDays.slice(0, 3).map((day) => {
                    const meta = CALENDAR_STATUS_META[day.status] || CALENDAR_STATUS_META.MISSING;
                    return (
                      <button
                        key={`queue-${day.report_date}`}
                        type="button"
                        onClick={() => handleCalendarDayClick(day)}
                        className={cx('grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-xs border px-2.5 py-2 text-left', meta.bg, meta.border)}
                      >
                        <span className="min-w-0">
                          <span className="block text-xs font-black text-gray-800">{day.report_date}</span>
                          <span className="mt-0.5 block text-[10px] text-gray-500">{day.weekday} · {meta.label}</span>
                        </span>
                        <span className={cx('grid h-6 w-6 place-items-center rounded-xs border bg-white', meta.text, meta.border)}>
                          <ChevronRight size={13} />
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-black text-gray-500">日期定位</div>
              <div className="flex gap-1.5 text-[10px] text-gray-400">
                <span>绿 已完成</span>
                <span>橙 待补</span>
              </div>
            </div>

            <div className="grid grid-cols-7 gap-1.5">
              {calendarLoading ? (
                Array.from({ length: 30 }).map((_, index) => (
                  <div key={index} className="h-7 rounded-xs bg-gray-100" />
                ))
              ) : (
                calendarDays.map((day) => {
                  const meta = CALENDAR_STATUS_META[day.status] || CALENDAR_STATUS_META.MISSING;
                  const isActive = selectedDate === day.report_date;
                  const isBusy = generatingDate === day.report_date;
                  return (
                    <button
                      key={day.report_date}
                      type="button"
                      onClick={() => handleCalendarDayClick(day)}
                      title={`${day.report_date} · ${meta.label}${day.takeaway ? ` · ${day.takeaway}` : ''}`}
                      className={cx(
                        'grid h-7 min-w-0 place-items-center rounded-xs border font-mono text-[11px] font-black shadow-none transition',
                        isActive ? `${meta.active} shadow-[0_6px_14px_rgba(15,23,42,0.12)]` : `${meta.bg} ${meta.border} ${meta.text}`,
                      )}
                    >
                      {isBusy ? <Loader2 size={12} className="animate-spin" /> : day.report_date.slice(8)}
                    </button>
                  );
                })
              )}
            </div>
          </Panel>

          <div className="flex-1 overflow-y-auto px-3 pb-3">
            <div className="flex items-center gap-2 px-0.5 pb-2 pt-1 text-[11px] font-black text-gray-500">
              <CheckCircle2 size={13} className="text-teal" />
              已生成记录
            </div>
            {datesLoading ? (
              <div className="px-2 py-5 text-center text-xs text-gray-400">加载中...</div>
            ) : generatedDates.length === 0 ? (
              <div className="px-2 py-5 text-center text-xs text-gray-400">暂无历史日报</div>
            ) : (
              generatedDates.map((d) => {
                const isActive = selectedDate === d.report_date;
                return (
                  <button
                    key={d.report_date}
                    type="button"
                    onClick={() => handleDateSelect(d.report_date)}
                    className={cx(
                      'mb-1.5 block w-full rounded-sm border px-3 py-2.5 text-left text-[13px] transition',
                      isActive ? 'border-gray-200 bg-white font-bold text-gray-900 shadow-[0_8px_22px_rgba(15,23,42,0.07)]' : 'border-transparent text-gray-600 hover:bg-white',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className={isActive ? 'text-gray-900' : 'text-gray-700'}>{d.report_date}</span>
                      <span className="text-[11px] text-gray-400">{EDITION_LABELS[d.edition || ''] || d.weekday}</span>
                    </div>
                    {d.takeaway && <div className="mt-1 truncate text-[11px] text-gray-400">{d.takeaway}</div>}
                    {d.status === 'ERROR' && (
                      <div className="mt-1 flex items-center justify-between">
                        <span className="inline-flex items-center gap-1 text-[10px] text-red">
                          <Circle size={7} className="fill-red" />生成失败
                        </span>
                        <span
                          onClick={(event) => {
                            event.stopPropagation();
                            generateForDate(d.report_date);
                          }}
                          className="text-[10px] font-black text-primary"
                        >
                          补生成
                        </span>
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,#F8FAFC_0%,#F4F6F8_44%,#EEF2F5_100%)] px-10 pb-10">
          <header className="sticky top-0 z-10 -mx-10 flex items-center justify-between gap-4 border-b border-gray-200 bg-[#F8FAFC]/90 px-10 py-4 backdrop-blur-md">
            <div>
              <div className="mb-1.5 flex items-center gap-3">
                <h1 className="m-0 text-lg font-black text-gray-900">AI 日报</h1>
                <ReportBadge>{editionLabel}</ReportBadge>
                {!isToday && report && <ReportBadge tone="history">历史回顾</ReportBadge>}
              </div>
              <p className="text-[13px] text-gray-400">
                {report
                  ? `${report.report_date} ${report.weekday}`
                  : displayDate
                    ? `${displayDate} ${displayWeekday} · ${displayMeta?.label || '待生成'}`
                    : '加载中...'}
                {report?.content_count ? ` · 基于 ${report.content_count} 条内容分析` : ''}
                {windowText ? ` · ${windowText}` : ''}
              </p>
            </div>
            {report && (
              <ReportActionButton onClick={handleRegenerate} loading={generating} icon={RefreshCw}>
                重新生成
              </ReportActionButton>
            )}
          </header>

          {loading ? (
            <ReportStatusPanel icon={FileText}>正在加载日报...</ReportStatusPanel>
          ) : error ? (
            <ReportStatusPanel
              icon={AlertTriangle}
              tone="error"
              action={(
                <ReportActionButton
                  onClick={() => generateForDate(recoveryDate)}
                  loading={generating && generatingDate === recoveryDate}
                  icon={RotateCcw}
                >
                  {mainActionLabel}
                </ReportActionButton>
              )}
            >
              {error}
            </ReportStatusPanel>
          ) : report?.status === 'ERROR' ? (
            <div className="grid min-h-[360px] place-items-center p-10 text-center">
              <div>
                <AlertTriangle size={30} className="mx-auto mb-3 text-red" strokeWidth={1.9} />
                <div className="mb-3 text-sm text-gray-500">{report.overview}</div>
                <ReportActionButton
                  onClick={() => generateForDate(report.report_date)}
                  loading={generating && generatingDate === report.report_date}
                  icon={RotateCcw}
                >
                  重试生成 {report.report_date}
                </ReportActionButton>
              </div>
            </div>
          ) : report?.status === 'GENERATING' ? (
            <ReportStatusPanel icon={Loader2}>日报生成中，请稍候...</ReportStatusPanel>
          ) : report ? (
            <article className="mx-auto mt-5 max-w-[760px] text-gray-900">
              <Panel className="relative overflow-hidden p-6 shadow-[0_18px_48px_rgba(15,23,42,0.06)]">
                <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,var(--color-primary),var(--color-teal))]" />
                <div className="relative flex items-start justify-between gap-5">
                  <div>
                    <div className="mb-4 flex items-center gap-2">
                      <span className="rounded-full border border-primary-border bg-primary-light px-2.5 py-1 font-mono text-[11px] font-black text-primary">
                        TOPIC RADAR DAILY
                      </span>
                      <span className="text-xs text-gray-500">{report.weekday}</span>
                      <span className="text-xs text-gray-500">{editionLabel}</span>
                    </div>
                    <h2 className="mb-3.5 text-[34px] font-black leading-none text-gray-900">
                      选题雷达<br />日报
                    </h2>
                    <p className="max-w-[520px] text-base font-bold leading-7 text-gray-700">
                      {report.takeaway || report.overview || '今日内容已完成归档，等待进一步分析。'}
                    </p>
                  </div>
                  <div className="min-w-28 rounded-sm border border-primary-border bg-primary-light px-3.5 py-3 text-right">
                    <div className="mb-1.5 text-[11px] text-gray-500">ISSUE DATE</div>
                    <div className="font-mono text-[22px] font-black text-primary">{report.report_date.slice(5)}</div>
                    <div className="mt-1 text-[11px] text-gray-500">{windowText || report.report_date.slice(0, 4)}</div>
                  </div>
                </div>
                <div className="relative mt-5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                  {[
                    { label: '内容样本', value: report.content_count || 0 },
                    { label: '完成分析', value: report.analyzed_count || 0 },
                    { label: '推荐选题', value: report.topic_count || pickList.length },
                    { label: '生成时间', value: generatedAt || '-' },
                  ].map((stat) => (
                    <StatBox key={stat.label} label={stat.label} value={stat.value} />
                  ))}
                </div>
              </Panel>

              <section className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_210px]">
                <Panel className="p-5">
                  <ReportSectionTitle icon={Newspaper} title="编辑摘要" />
                  <p className="text-sm leading-8 text-gray-600">{report.overview || '暂无概述。'}</p>
                </Panel>
                <Panel className="p-4.5">
                  <div className="mb-3 flex items-center gap-2 text-[13px] font-black text-gray-900">
                    <KeyRound size={14} className="text-primary" strokeWidth={2.2} />
                    今日关键词
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {keywordList.length > 0 ? keywordList.map((kw, i) => (
                      <span
                        key={`${kw}-${i}`}
                        className={cx(
                          'rounded-full border px-2.5 py-1 text-xs font-bold',
                          i === 0 ? 'border-primary-border bg-primary-light text-gray-700' : 'border-gray-200 bg-gray-50 text-gray-700',
                        )}
                      >
                        {kw}
                      </span>
                    )) : <span className="text-xs text-gray-400">暂无关键词</span>}
                  </div>
                </Panel>
              </section>

              {leadPick && (
                <Panel className="mt-4 overflow-hidden">
                  <div className="flex items-stretch border-b border-gray-100">
                    <div className="flex w-24 shrink-0 flex-col items-center justify-center gap-1 border-r border-gray-100 bg-orange-50">
                      <Target size={18} className="text-primary" strokeWidth={2.2} />
                      <div className="text-[10px] font-black text-primary">今日主推</div>
                      <div className="font-mono text-3xl font-black text-primary">{leadPick.score || 1}</div>
                    </div>
                    <div className="min-w-0 flex-1 p-5">
                      <div className="flex items-start gap-2">
                        <h3 className="m-0 flex-1 text-lg font-black leading-7 text-gray-900">{leadPick.title}</h3>
                        {leadPick.source_url && (
                          <a href={leadPick.source_url} target="_blank" rel="noopener noreferrer" title="查看原文" className="mt-1 text-gray-400 hover:text-primary">
                            <ExternalLink size={15} strokeWidth={2} />
                          </a>
                        )}
                      </div>
                      <p className="mt-2 text-[13px] leading-7 text-gray-500">{leadPick.reason}</p>
                      {(leadPick.platforms ?? []).length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {(leadPick.platforms ?? []).map((p, j) => (
                            <span key={`${p}-${j}`} className="rounded-full border border-teal-border bg-teal-light px-2 py-0.5 text-[11px] text-teal">
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  {secondaryPicks.length > 0 && (
                    <div className="px-4.5 pb-3 pt-2">
                      {secondaryPicks.map((pick, i) => (
                        <div key={`${pick.title}-${i}`} className="grid grid-cols-[28px_minmax(0,1fr)_42px] items-start gap-2.5 border-b border-gray-100 py-3 last:border-b-0">
                          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gray-100 font-mono text-[11px] font-black text-gray-600">{i + 2}</div>
                          <div className="min-w-0">
                            <div className="text-sm font-bold leading-6 text-gray-900">{pick.title}</div>
                            <div className="mt-0.5 text-xs leading-5 text-gray-500">{pick.reason}</div>
                          </div>
                          <div className="text-right font-mono text-lg font-black text-primary">{pick.score || '-'}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              )}

              {trendList.length > 0 && (
                <Panel className="mt-4 p-5">
                  <ReportSectionTitle icon={TrendingUp} title="内容趋势" />
                  <div>
                    {trendList.map((trend, i) => (
                      <div key={`${trend.title}-${i}`} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 border-t border-gray-100 py-3.5 first:border-t-0">
                        <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-primary font-mono text-xs font-black text-white">
                          {String(i + 1).padStart(2, '0')}
                        </div>
                        <div>
                          <div className="mb-1 text-[15px] font-black text-gray-900">{trend.title}</div>
                          <div className="text-[13px] leading-7 text-gray-500">{trend.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              )}

              {platformTipEntries.length > 0 && (
                <section className="mb-6 mt-4">
                  <ReportSectionTitle icon={Lightbulb} title="平台创作建议" />
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {platformTipEntries.map(([platform, tips]) => (
                      <Panel key={platform} className="p-4.5">
                        <PlatformHeading icon={Smartphone} label={platform} />
                        {(Array.isArray(tips) ? tips : []).map((tip: string, j: number) => (
                          <div
                            key={`${platform}-${j}`}
                            className={cx('mb-2 border-l-2 pl-2.5 text-xs leading-6 text-gray-500', j === 0 ? 'border-primary-border' : 'border-gray-200')}
                          >
                            {tip}
                          </div>
                        ))}
                      </Panel>
                    ))}
                  </div>
                </section>
              )}

              <div className="flex flex-wrap gap-4 border-t border-gray-200 pt-3.5 text-xs text-gray-400">
                <ReportFooterStat icon={CalendarDays}>{report.report_date} {report.weekday}</ReportFooterStat>
                <ReportFooterStat icon={BarChart3}>分析 {report.analyzed_count} 条内容</ReportFooterStat>
                <ReportFooterStat icon={Target}>推荐 {report.topic_count} 个选题</ReportFooterStat>
              </div>
            </article>
          ) : (
            <ReportStatusPanel
              icon={Inbox}
              action={(
                <ReportActionButton
                  onClick={() => generateForDate(recoveryDate)}
                  loading={generating && generatingDate === recoveryDate}
                  icon={FileText}
                >
                  {mainActionLabel}
                </ReportActionButton>
              )}
            >
              暂无日报数据
            </ReportStatusPanel>
          )}
        </main>
      </div>
    </div>
  );
}
