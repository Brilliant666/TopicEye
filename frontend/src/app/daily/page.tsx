'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  ExternalLink,
  FileText,
  Inbox,
  KeyRound,
  Lightbulb,
  Loader2,
  Newspaper,
  Pin,
  RefreshCw,
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

const EDITION_LABELS: Record<string, string> = {
  noon: '午间快照',
  evening: '晚间快照',
  snapshot: '实时快照',
  manual: '手动快照',
  final: '完整复盘',
  legacy: '历史日报',
};

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
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [datesLoading, setDatesLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch available dates list
  useEffect(() => {
    (async () => {
      try {
        setDatesLoading(true);
        const data = await dailyReportApi.listDates();
        setDates(data.dates || []);
      } catch {
        // Silent fail — dates sidebar is non-critical
      } finally {
        setDatesLoading(false);
      }
    })();
  }, []);

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

  const handleRegenerate = async () => {
    try {
      setGenerating(true);
      const data = await dailyReportApi.generateVersion({ edition: 'manual', force: true });
      setReport(data as unknown as DailyReportData);
      // Refresh dates list
      const datesData = await dailyReportApi.listDates();
      setDates(datesData.dates || []);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : '生成失败';
      setError(errMsg);
    } finally {
      setGenerating(false);
    }
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

  const todayStr = new Date().toISOString().slice(0, 10);
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

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
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
        <ReportSidebarHeader icon={CalendarDays} title="历史日报" countText={`共 ${dates.length} 期`} />

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

        {/* Date list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '4px 12px 12px',
        }}>
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
                    <span style={{ fontSize: 10, color: T.red, marginTop: 2, display: 'inline-block' }}>
                      生成失败
                    </span>
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
              {report ? `${report.report_date} ${report.weekday}` : '加载中...'}
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
          <ReportStatusPanel icon={AlertTriangle} tone="error">{error}</ReportStatusPanel>
        ) : report?.status === 'ERROR' ? (
          <div style={{ textAlign: 'center', padding: 80 }}>
            <AlertTriangle size={30} color={T.red} strokeWidth={1.9} style={{ marginBottom: 12 }} />
            <div style={{ color: T.gray500, fontSize: 14, marginBottom: 12 }}>{report.overview}</div>
            <ReportActionButton
              onClick={handleRegenerate}
              loading={generating}
              icon={RefreshCw}
            >
              重试生成
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
              background: '#111827',
              border: '1px solid #1F2937',
              borderRadius: T.radius,
              padding: '24px 28px 22px',
              color: T.white,
              boxShadow: '0 22px 60px rgba(15, 23, 42, 0.16)',
            }}>
              <div style={{
                position: 'absolute',
                right: -90,
                top: -130,
                width: 260,
                height: 260,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(255, 107, 53, 0.32), rgba(255, 107, 53, 0) 66%)',
              }} />
              <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                    <span style={{
                      fontSize: 11,
                      fontWeight: 800,
                      color: '#FDBA74',
                      border: '1px solid rgba(253, 186, 116, 0.36)',
                      borderRadius: 999,
                      padding: '4px 9px',
                      fontFamily: T.mono,
                    }}>
                      TOPIC RADAR DAILY
                    </span>
                    <span style={{ fontSize: 12, color: '#CBD5E1' }}>{report.weekday}</span>
                    <span style={{ fontSize: 12, color: '#CBD5E1' }}>{editionLabel}</span>
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
                    color: '#F8FAFC',
                  }}>
                    {report.takeaway || report.overview || '今日内容已完成归档，等待进一步分析。'}
                  </p>
                </div>
                <div style={{
                  minWidth: 112,
                  padding: '12px 14px',
                  border: '1px solid rgba(148, 163, 184, 0.28)',
                  borderRadius: T.radiusSm,
                  background: 'rgba(15, 23, 42, 0.62)',
                  textAlign: 'right',
                }}>
                  <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 6 }}>ISSUE DATE</div>
                  <div style={{ fontSize: 22, fontFamily: T.mono, fontWeight: 700 }}>{report.report_date.slice(5)}</div>
                  <div style={{ fontSize: 11, color: '#CBD5E1', marginTop: 4 }}>{windowText || report.report_date.slice(0, 4)}</div>
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
                    background: 'rgba(255, 255, 255, 0.08)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                  }}>
                    <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 5 }}>{stat.label}</div>
                    <div style={{ fontSize: 19, fontWeight: 800, fontFamily: T.mono }}>{stat.value}</div>
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
                onClick={handleRegenerate}
                loading={generating}
                icon={FileText}
              >
                生成今日日报
              </ReportActionButton>
            )}
          >
            暂无日报数据
          </ReportStatusPanel>
        )}
      </div>
    </div>
  );
}
