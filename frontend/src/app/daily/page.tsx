'use client';

import React, { useState, useEffect, useCallback } from 'react';
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
import { T } from '@/lib/design-tokens';
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

const CALENDAR_STATUS_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  DONE: { label: '已完成', color: '#0F766E', bg: '#ECFDF5', border: '#99F6E4' },
  ERROR: { label: '失败', color: '#DC2626', bg: '#FEF2F2', border: '#FECACA' },
  MISSING: { label: '缺失', color: '#D97706', bg: '#FFFBEB', border: '#FDE68A' },
  GENERATING: { label: '生成中', color: '#2563EB', bg: '#EFF6FF', border: '#BFDBFE' },
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

  // Fetch available dates list and recovery map
  useEffect(() => {
    (async () => {
      try {
        setDatesLoading(true);
        setCalendarLoading(true);
        await refreshReportIndexes();
      } catch {
        // Sidebar is non-critical; the main report still loads independently.
      } finally {
        setDatesLoading(false);
        setCalendarLoading(false);
      }
    })();
  }, [refreshReportIndexes]);

  // Fetch report for a given date (or today)
  const fetchReport = useCallback(async (date?: string) => {
    try {
      setLoading(true);
      setError(null);
      let data: DailyReportData;
      if (date) {
        data = await dailyReportApi.getByDate(date) as unknown as DailyReportData;
      } else {
        data = await dailyReportApi.getToday() as unknown as DailyReportData;
      }
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

  // Load today's report initially
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
      const errMsg = err instanceof Error ? err.message : '生成失败';
      setError(errMsg);
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

  // Parse JSON strings if needed
  const parseJson = (val: unknown) => {
    if (typeof val === 'string') {
      try { return JSON.parse(val); } catch { return null; }
    }
    return val;
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

  return (
    <div style={{ width: '100%', height: '100%', overflowX: 'auto', overflowY: 'hidden' }}>
      <div style={{ display: 'flex', height: '100%', minWidth: 1040, overflow: 'hidden' }}>
        {/* Left Sidebar — Date History */}
        <div style={{
          width: 260,
          minWidth: 260,
          borderRight: '1px solid #D8DEE8',
          background: 'linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 34%, #F8FAFC 100%)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
        {/* Sidebar header */}
        <ReportSidebarHeader
          icon={CalendarDays}
          title="日报补录中心"
          countText={`近 30 天 · 待处理 ${recoveryDays.length}`}
        />

        {/* Today button */}
        <div style={{ padding: '8px 12px 4px' }}>
          <CurrentPeriodButton
            active={selectedDate === todayStr || !selectedDate}
            icon={Pin}
            onClick={() => fetchReport()}
          >
            今天
          </CurrentPeriodButton>
        </div>

        <div style={{
          margin: '8px 12px 10px',
          padding: 12,
          background: T.white,
          border: `1px solid ${T.gray200}`,
          borderRadius: T.radius,
          boxShadow: '0 8px 22px rgba(15, 23, 42, 0.04)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 850, color: T.gray800 }}>待补录任务</div>
              <div style={{ fontSize: 11, color: T.gray400, marginTop: 2 }}>
                {nextRecoveryDay ? `下一天 ${nextRecoveryDay.report_date}` : '近 30 天已闭环'}
              </div>
            </div>
            <button
              type="button"
              onClick={() => refreshReportIndexes()}
              title="刷新时间地图"
              style={{
                width: 26,
                height: 26,
                border: `1px solid ${T.gray200}`,
                borderRadius: 7,
                background: T.gray50,
                color: T.gray500,
                display: 'grid',
                placeItems: 'center',
                cursor: 'pointer',
              }}
            >
              <RefreshCw size={13} />
            </button>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 8,
            marginBottom: 10,
          }}>
            <div style={{
              padding: '10px 11px',
              borderRadius: T.radiusSm,
              background: T.primaryLight,
              border: `1px solid ${T.primaryBorder}`,
            }}>
              <div style={{ fontSize: 10, color: T.gray500, marginBottom: 4 }}>缺失日报</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: T.primary, fontFamily: T.mono }}>
                {calendarStats.missing}
              </div>
            </div>
            <div style={{
              padding: '10px 11px',
              borderRadius: T.radiusSm,
              background: T.redLight,
              border: `1px solid #FECACA`,
            }}>
              <div style={{ fontSize: 10, color: T.gray500, marginBottom: 4 }}>生成失败</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: T.red, fontFamily: T.mono }}>
                {calendarStats.error}
              </div>
            </div>
          </div>

          {nextRecoveryDay ? (
            <button
              type="button"
              disabled={generating}
              onClick={() => generateForDate(nextRecoveryDay.report_date)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 10,
                padding: '10px 11px',
                marginBottom: 12,
                border: `1px solid ${T.primaryBorder}`,
                borderRadius: T.radiusSm,
                background: T.primary,
                color: T.white,
                cursor: generating ? 'wait' : 'pointer',
                textAlign: 'left',
              }}
            >
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 12, fontWeight: 850 }}>补生成最近遗漏</span>
                <span style={{ display: 'block', fontSize: 11, opacity: 0.82, marginTop: 2 }}>
                  {nextRecoveryDay.report_date} {nextRecoveryDay.weekday}
                </span>
              </span>
              {generatingDate === nextRecoveryDay.report_date
                ? <Loader2 size={15} className="fanqie-spin" />
                : <RotateCcw size={15} />}
            </button>
          ) : (
            <div style={{
              padding: '10px 11px',
              marginBottom: 12,
              border: `1px solid ${T.tealBorder}`,
              borderRadius: T.radiusSm,
              background: T.tealLight,
              color: T.teal,
              fontSize: 12,
              fontWeight: 800,
            }}>
              最近 30 天无需补录
            </div>
          )}

          {recoveryDays.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: T.gray500, marginBottom: 6 }}>待补录队列</div>
              <div style={{ display: 'grid', gap: 6 }}>
                {recoveryDays.slice(0, 3).map((day) => {
                  const meta = CALENDAR_STATUS_META[day.status] || CALENDAR_STATUS_META.MISSING;
                  return (
                    <button
                      key={`queue-${day.report_date}`}
                      type="button"
                      onClick={() => handleCalendarDayClick(day)}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'minmax(0, 1fr) auto',
                        alignItems: 'center',
                        gap: 8,
                        width: '100%',
                        padding: '8px 9px',
                        border: `1px solid ${meta.border}`,
                        borderRadius: T.radiusXs,
                        background: meta.bg,
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'block', fontSize: 12, fontWeight: 850, color: T.gray800 }}>
                          {day.report_date}
                        </span>
                        <span style={{ display: 'block', fontSize: 10, color: T.gray500, marginTop: 2 }}>
                          {day.weekday} · {meta.label}
                        </span>
                      </span>
                      <span style={{
                        width: 24,
                        height: 24,
                        borderRadius: 7,
                        display: 'grid',
                        placeItems: 'center',
                        background: T.white,
                        color: meta.color,
                        border: `1px solid ${meta.border}`,
                      }}>
                        <ChevronRight size={13} />
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: T.gray500 }}>日期定位</div>
            <div style={{ display: 'flex', gap: 6, fontSize: 10, color: T.gray400 }}>
              <span>绿 已完成</span>
              <span>橙 待补</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 5 }}>
            {calendarLoading ? (
              Array.from({ length: 30 }).map((_, index) => (
                <div key={index} style={{ height: 28, borderRadius: 7, background: T.gray100 }} />
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
                    style={{
                      height: 28,
                      minWidth: 0,
                      borderRadius: 7,
                      border: `1px solid ${isActive ? meta.color : meta.border}`,
                      background: isActive ? meta.color : meta.bg,
                      color: isActive ? T.white : meta.color,
                      fontSize: 11,
                      fontWeight: 850,
                      fontFamily: T.mono,
                      cursor: 'pointer',
                      display: 'grid',
                      placeItems: 'center',
                      boxShadow: isActive ? '0 6px 14px rgba(15, 23, 42, 0.12)' : 'none',
                    }}
                  >
                    {isBusy ? <Loader2 size={12} className="fanqie-spin" /> : day.report_date.slice(8)}
                  </button>
                );
              })
            )}
          </div>

        </div>

        {/* Date list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '0 12px 12px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 2px 8px', color: T.gray500, fontSize: 11, fontWeight: 800 }}>
            <CheckCircle2 size={13} color={T.teal} />
            已生成记录
          </div>
          {datesLoading ? (
            <div style={{ padding: '20px 8px', textAlign: 'center', fontSize: 12, color: T.gray400 }}>
              加载中...
            </div>
          ) : dates.length === 0 ? (
            <div style={{ padding: '20px 8px', textAlign: 'center', fontSize: 12, color: T.gray400 }}>
              暂无历史日报
            </div>
          ) : (
            dates.map((d) => {
              const isActive = selectedDate === d.report_date;
              const isDateToday = d.report_date === todayStr;
              if (isDateToday) return null; // shown via button above
              return (
                <button
                  key={d.report_date}
                  onClick={() => handleDateSelect(d.report_date)}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '11px 12px',
                    marginBottom: 6,
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? T.gray900 : T.gray600,
                    background: isActive ? T.white : 'transparent',
                    border: isActive ? `1px solid ${T.gray200}` : '1px solid transparent',
                    borderRadius: T.radiusSm,
                    cursor: 'pointer',
                    transition: 'all 0.12s',
                    textAlign: 'left',
                    boxShadow: isActive ? '0 8px 22px rgba(15, 23, 42, 0.07)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: isActive ? T.gray900 : T.gray700 }}>
                      {d.report_date}
                    </span>
                    <span style={{ fontSize: 11, color: T.gray400 }}>{EDITION_LABELS[d.edition || ''] || d.weekday}</span>
                  </div>
                  {d.takeaway && (
                    <div style={{
                      fontSize: 11, color: T.gray400, marginTop: 3,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {d.takeaway}
                    </div>
                  )}
                  {d.status === 'ERROR' && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
                      <span style={{ fontSize: 10, color: T.red, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Circle size={7} fill={T.red} />生成失败
                      </span>
                      <span
                        onClick={(event) => {
                          event.stopPropagation();
                          generateForDate(d.report_date);
                        }}
                        style={{ fontSize: 10, color: T.primary, fontWeight: 800 }}
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
      </div>

      {/* Main Content */}
      <div style={{
        flex: 1,
        padding: '0 40px 42px',
        overflowY: 'auto',
        background: 'linear-gradient(180deg, #F8FAFC 0%, #F4F6F8 44%, #EEF2F5 100%)',
      }}>
        {/* Header */}
        <div style={{
          position: 'sticky',
          top: 0,
          zIndex: 2,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '0 -40px 0',
          padding: '18px 40px',
          background: 'rgba(248, 250, 252, 0.9)',
          borderBottom: `1px solid ${T.gray200}`,
          backdropFilter: 'blur(14px)',
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
              <h1 style={{ fontSize: 18, fontWeight: 800, color: T.gray900 }}>AI 日报</h1>
              <ReportBadge>{editionLabel}</ReportBadge>
              {!isToday && report && (
                <ReportBadge tone="history">历史回顾</ReportBadge>
              )}
            </div>
            <p style={{ fontSize: 13, color: T.gray400 }}>
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
            <ReportActionButton
              onClick={handleRegenerate}
              loading={generating}
              icon={RefreshCw}
            >
              重新生成
            </ReportActionButton>
          )}
        </div>

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
          <div style={{ textAlign: 'center', padding: 80 }}>
            <AlertTriangle size={30} color={T.red} strokeWidth={1.9} style={{ marginBottom: 12 }} />
            <div style={{ color: T.gray500, fontSize: 14, marginBottom: 12 }}>{report.overview}</div>
            <ReportActionButton
              onClick={() => generateForDate(report.report_date)}
              loading={generating && generatingDate === report.report_date}
              icon={RotateCcw}
            >
              重试生成 {report.report_date}
            </ReportActionButton>
          </div>
        ) : report?.status === 'GENERATING' ? (
          <ReportStatusPanel icon={Loader2}>日报生成中，请稍候...</ReportStatusPanel>
        ) : report ? (
          <article style={{
            maxWidth: 760,
            margin: '22px auto 0',
            color: T.gray900,
          }}>
            <section style={{
              position: 'relative',
              overflow: 'hidden',
              background: T.white,
              border: `1px solid ${T.gray200}`,
              borderRadius: T.radius,
              padding: '24px 28px 22px',
              color: T.gray900,
              boxShadow: '0 18px 48px rgba(15, 23, 42, 0.06)',
            }}>
              <div style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: 0,
                height: 4,
                background: `linear-gradient(90deg, ${T.primary}, ${T.teal})`,
              }} />
              <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 800,
                      color: T.primary,
                      background: T.primaryLight,
                      border: `1px solid ${T.primaryBorder}`,
                      borderRadius: 999,
                      padding: '4px 9px',
                      fontFamily: T.mono,
                    }}>
                      TOPIC RADAR DAILY
                    </span>
                    <span style={{ fontSize: 12, color: T.gray500 }}>{report.weekday}</span>
                    <span style={{ fontSize: 12, color: T.gray500 }}>{editionLabel}</span>
                  </div>
                  <h2 style={{
                    fontSize: 34,
                    lineHeight: 1,
                    fontWeight: 900,
                    letterSpacing: 0,
                    marginBottom: 14,
                  }}>
                    选题雷达<br />日报
                  </h2>
                  <p style={{
                    maxWidth: 520,
                    fontSize: 16,
                    lineHeight: 1.65,
                    fontWeight: 700,
                    color: T.gray700,
                  }}>
                    {report.takeaway || report.overview || '今日内容已完成归档，等待进一步分析。'}
                  </p>
                </div>
                <div style={{
                  minWidth: 112,
                  padding: '12px 14px',
                  border: `1px solid ${T.primaryBorder}`,
                  borderRadius: T.radiusSm,
                  background: T.primaryLight,
                  textAlign: 'right',
                }}>
                  <div style={{ fontSize: 11, color: T.gray500, marginBottom: 6 }}>ISSUE DATE</div>
                  <div style={{ fontSize: 22, fontFamily: T.mono, fontWeight: 800, color: T.primary }}>{report.report_date.slice(5)}</div>
                  <div style={{ fontSize: 11, color: T.gray500, marginTop: 4 }}>{windowText || report.report_date.slice(0, 4)}</div>
                </div>
              </div>
              <div style={{
                position: 'relative',
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 10,
                marginTop: 20,
              }}>
                {[
                  { label: '内容样本', value: report.content_count || 0 },
                  { label: '完成分析', value: report.analyzed_count || 0 },
                  { label: '推荐选题', value: report.topic_count || pickList.length },
                  { label: '生成时间', value: generatedAt || '-' },
                ].map((stat) => (
                  <div key={stat.label} style={{
                    padding: '10px 12px',
                    borderRadius: T.radiusSm,
                    background: T.gray50,
                    border: `1px solid ${T.gray200}`,
                  }}>
                    <div style={{ fontSize: 11, color: T.gray500, marginBottom: 5 }}>{stat.label}</div>
                    <div style={{ fontSize: 19, fontWeight: 800, fontFamily: T.mono, color: T.gray900 }}>{stat.value}</div>
                  </div>
                ))}
              </div>
            </section>

            <section style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) 210px',
              gap: 16,
              marginTop: 18,
            }}>
              <div style={{
                padding: '20px 22px',
                background: T.white,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radius,
              }}>
                <ReportSectionTitle icon={Newspaper} title="编辑摘要" />
                <p style={{ fontSize: 14, color: T.gray600, lineHeight: 1.85 }}>
                  {report.overview || '暂无概述。'}
                </p>
              </div>
              <div style={{
                padding: '18px 18px',
                background: T.white,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radius,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 800, color: T.gray900, marginBottom: 12 }}>
                  <KeyRound size={14} color={T.primary} strokeWidth={2.2} />
                  今日关键词
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                  {keywordList.length > 0 ? keywordList.map((kw, i) => (
                    <span key={`${kw}-${i}`} style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: T.gray700,
                      background: i === 0 ? T.primaryLight : T.gray50,
                      border: `1px solid ${i === 0 ? T.primaryBorder : T.gray200}`,
                      padding: '5px 9px',
                      borderRadius: 999,
                    }}>
                      {kw}
                    </span>
                  )) : (
                    <span style={{ fontSize: 12, color: T.gray400 }}>暂无关键词</span>
                  )}
                </div>
              </div>
            </section>

            {leadPick && (
              <section style={{
                marginTop: 18,
                background: T.white,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radius,
                overflow: 'hidden',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'stretch',
                  borderBottom: `1px solid ${T.gray100}`,
                }}>
                  <div style={{
                    width: 94,
                    flexShrink: 0,
                    background: '#FFF7ED',
                    borderRight: `1px solid ${T.gray100}`,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 4,
                  }}>
                    <Target size={18} color={T.primary} strokeWidth={2.2} />
                    <div style={{ fontSize: 10, fontWeight: 800, color: T.primary }}>今日主推</div>
                    <div style={{ fontSize: 30, fontWeight: 900, color: T.primary, fontFamily: T.mono }}>
                      {leadPick.score || 1}
                    </div>
                  </div>
                  <div style={{ padding: '20px 22px', minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <h3 style={{ fontSize: 18, lineHeight: 1.45, fontWeight: 800, color: T.gray900, flex: 1 }}>
                        {leadPick.title}
                      </h3>
                      {leadPick.source_url && (
                        <a
                          href={leadPick.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="查看原文"
                          style={{ color: T.gray400, lineHeight: 0, marginTop: 4 }}
                        >
                          <ExternalLink size={15} strokeWidth={2} />
                        </a>
                      )}
                    </div>
                    <p style={{ fontSize: 13, color: T.gray500, lineHeight: 1.75, marginTop: 8 }}>{leadPick.reason}</p>
                    {(leadPick.platforms ?? []).length > 0 && (
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
                        {(leadPick.platforms ?? []).map((p, j) => (
                          <span key={`${p}-${j}`} style={{
                            fontSize: 11,
                            color: T.teal,
                            background: T.tealLight,
                            border: `1px solid ${T.tealBorder}`,
                            padding: '3px 8px',
                            borderRadius: 999,
                          }}>
                            {p}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {secondaryPicks.length > 0 && (
                  <div style={{ padding: '8px 18px 14px' }}>
                    {secondaryPicks.map((pick, i) => (
                      <div key={`${pick.title}-${i}`} style={{
                        display: 'grid',
                        gridTemplateColumns: '28px minmax(0, 1fr) 42px',
                        gap: 10,
                        alignItems: 'start',
                        padding: '13px 0',
                        borderBottom: i === secondaryPicks.length - 1 ? 'none' : `1px solid ${T.gray100}`,
                      }}>
                        <div style={{
                          width: 24,
                          height: 24,
                          borderRadius: 999,
                          background: T.gray100,
                          color: T.gray600,
                          fontSize: 11,
                          fontWeight: 800,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: T.mono,
                        }}>
                          {i + 2}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: T.gray900, lineHeight: 1.5 }}>{pick.title}</div>
                          <div style={{ fontSize: 12, color: T.gray500, lineHeight: 1.6, marginTop: 3 }}>{pick.reason}</div>
                        </div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: T.primary, fontFamily: T.mono, textAlign: 'right' }}>
                          {pick.score || '-'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {trendList.length > 0 && (
              <section style={{
                marginTop: 18,
                padding: '20px 22px',
                background: T.white,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radius,
              }}>
                <ReportSectionTitle icon={TrendingUp} title="内容趋势" />
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {trendList.map((trend, i) => (
                    <div key={`${trend.title}-${i}`} style={{
                      display: 'grid',
                      gridTemplateColumns: '34px minmax(0, 1fr)',
                      gap: 12,
                      padding: '14px 0',
                      borderTop: i === 0 ? 'none' : `1px solid ${T.gray100}`,
                    }}>
                      <div style={{
                        width: 28,
                        height: 28,
                        borderRadius: 8,
                        background: trend.color || T.primary,
                        color: T.white,
                        fontSize: 12,
                        fontWeight: 900,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontFamily: T.mono,
                      }}>
                        {String(i + 1).padStart(2, '0')}
                      </div>
                      <div>
                        <div style={{ fontSize: 15, fontWeight: 800, color: T.gray900, marginBottom: 4 }}>{trend.title}</div>
                        <div style={{ fontSize: 13, color: T.gray500, lineHeight: 1.7 }}>{trend.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {platformTipEntries.length > 0 && (
              <section style={{ marginTop: 18, marginBottom: 24 }}>
                <ReportSectionTitle icon={Lightbulb} title="平台创作建议" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                  {platformTipEntries.map(([platform, tips]) => (
                    <div key={platform} style={{
                      padding: '16px 18px',
                      background: T.white,
                      borderRadius: T.radius,
                      border: `1px solid ${T.gray200}`,
                    }}>
                      <PlatformHeading icon={Smartphone} label={platform} />
                      {(Array.isArray(tips) ? tips : []).map((tip: string, j: number) => (
                        <div key={`${platform}-${j}`} style={{
                          fontSize: 12,
                          color: T.gray500,
                          lineHeight: 1.65,
                          marginBottom: 8,
                          paddingLeft: 10,
                          borderLeft: `2px solid ${j === 0 ? T.primaryBorder : T.gray200}`,
                        }}>
                          {tip}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </section>
            )}

            <div style={{
              padding: '14px 0 0',
              display: 'flex',
              flexWrap: 'wrap',
              gap: 18,
              fontSize: 12,
              color: T.gray400,
              borderTop: `1px solid ${T.gray200}`,
            }}>
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
      </div>
    </div>
    </div>
  );
}
