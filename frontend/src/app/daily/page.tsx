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
      const data = await dailyReportApi.regenerate();
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

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left Sidebar — Date History */}
      <div style={{
        width: 260,
        minWidth: 260,
        borderRight: `1px solid ${T.gray200}`,
        background: T.white,
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
                    padding: '10px 12px',
                    marginBottom: 2,
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? T.gray900 : T.gray600,
                    background: isActive ? T.primaryLight : 'transparent',
                    border: 'none',
                    borderRadius: T.radiusXs,
                    cursor: 'pointer',
                    transition: 'all 0.12s',
                    textAlign: 'left',
                    borderLeft: isActive ? `3px solid ${T.primary}` : '3px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, color: isActive ? T.gray900 : T.gray700 }}>
                      {d.report_date}
                    </span>
                    <span style={{ fontSize: 11, color: T.gray400 }}>{d.weekday}</span>
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
      <div style={{ flex: 1, padding: '32px 40px', overflowY: 'auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
              <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>AI 日报</h1>
              <ReportBadge>DAILY REPORT</ReportBadge>
              {!isToday && report && (
                <ReportBadge tone="history">历史回顾</ReportBadge>
              )}
            </div>
            <p style={{ fontSize: 13, color: T.gray400 }}>
              {report ? `${report.report_date} ${report.weekday}` : '加载中...'}
              {report?.content_count ? ` · 基于 ${report.content_count} 条内容分析` : ''}
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
          <div style={{ maxWidth: 800 }}>
            {/* Takeaway */}
            {report.takeaway && (
              <div style={{
                background: `linear-gradient(135deg, ${T.primary}10, #8B5CF610)`,
                borderRadius: T.radius, padding: '20px 24px',
                marginBottom: 24, borderLeft: `4px solid ${T.primary}`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: T.primary, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  今日要点
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: T.gray900, lineHeight: 1.6 }}>
                  {report.takeaway}
                </div>
              </div>
            )}

            {/* Overview */}
            {report.overview && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Newspaper} title="今日概述" />
                <p style={{ fontSize: 14, color: T.gray600, lineHeight: 1.8 }}>{report.overview}</p>
              </div>
            )}

            {/* Keywords */}
            {keywords?.length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={KeyRound} title="今日关键词" />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {keywords.map((kw: string, i: number) => (
                    <span key={i} style={{
                      fontSize: 13, fontWeight: 500, color: T.gray700,
                      background: T.gray50, border: `1px solid ${T.gray200}`,
                      padding: '4px 14px', borderRadius: 20,
                    }}>
                      {kw}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Trends */}
            {trends?.length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={TrendingUp} title="内容趋势" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {trends.map((trend: { title: string; desc: string; color?: string }, i: number) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 12,
                      padding: '14px 18px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: trend.color || T.primary, marginTop: 5, flexShrink: 0,
                      }} />
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, marginBottom: 2 }}>{trend.title}</div>
                        <div style={{ fontSize: 13, color: T.gray500 }}>{trend.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top Picks */}
            {topPicks?.length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Target} title="精选选题推荐" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {topPicks.map((pick: { title: string; reason: string; score?: number; platforms?: string[]; source_url?: string }, i: number) => (
                    <div key={i} style={{
                      padding: '16px 20px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            <span style={{
                              fontSize: 11, fontWeight: 700, color: T.white,
                              background: i === 0 ? '#FF6B35' : i === 1 ? '#F59E0B' : T.primary,
                              width: 22, height: 22, borderRadius: '50%',
                              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                            }}>
                              {i + 1}
                            </span>
                            <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900 }}>{pick.title}</span>
                            {pick.source_url && (
                              <a
                                href={pick.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="查看原文"
                                style={{
                                  fontSize: 13, color: T.gray400,
                                  textDecoration: 'none', flexShrink: 0,
                                  cursor: 'pointer',
                                }}
                              >
                                <ExternalLink size={13} strokeWidth={2} />
                              </a>
                            )}
                          </div>
                          <div style={{ fontSize: 12, color: T.gray500, marginLeft: 30 }}>{pick.reason}</div>
                          {(pick.platforms ?? []).length > 0 && (
                            <div style={{ display: 'flex', gap: 6, marginTop: 6, marginLeft: 30 }}>
                              {(pick.platforms ?? []).map((p: string, j: number) => (
                                <span key={j} style={{
                                  fontSize: 10, color: T.teal, background: T.tealLight,
                                  padding: '1px 8px', borderRadius: 4,
                                }}>
                                  {p}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        {pick.score && (
                          <div style={{
                            fontSize: 22, fontWeight: 800, color: T.primary,
                            fontFamily: T.mono, marginLeft: 16,
                          }}>
                            {pick.score}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Platform Tips */}
            {platformTips && typeof platformTips === 'object' && (
              <div style={{ marginBottom: 40 }}>
                <ReportSectionTitle icon={Lightbulb} title="平台创作建议" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
                  {Object.entries(platformTips).map(([platform, tips]: [string, unknown]) => (
                    <div key={platform} style={{
                      padding: '16px 20px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <PlatformHeading icon={Smartphone} label={platform} />
                      {(Array.isArray(tips) ? tips : []).map((tip: string, j: number) => (
                        <div key={j} style={{ fontSize: 12, color: T.gray500, lineHeight: 1.6, marginBottom: 4, paddingLeft: 10, borderLeft: `2px solid ${T.gray200}` }}>
                          {tip}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Stats footer */}
            <div style={{
              padding: '16px 20px', background: T.gray50, borderRadius: T.radiusSm,
              display: 'flex', gap: 24, fontSize: 12, color: T.gray400,
            }}>
              <ReportFooterStat icon={CalendarDays}>{report.report_date} {report.weekday}</ReportFooterStat>
              <ReportFooterStat icon={BarChart3}>分析 {report.analyzed_count} 条内容</ReportFooterStat>
              <ReportFooterStat icon={Target}>推荐 {report.topic_count} 个选题</ReportFooterStat>
            </div>
          </div>
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
