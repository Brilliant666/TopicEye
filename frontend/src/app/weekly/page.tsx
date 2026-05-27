'use client';

import React, { useState, useEffect, useCallback } from 'react';
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
import { T } from '@/lib/design-tokens';
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

export default function WeeklyDigestPage() {
  const [digest, setDigest] = useState<WeeklyDigest | null>(null);
  const [weeks, setWeeks] = useState<WeeklyDigestWeekSummary[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [weeksLoading, setWeeksLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch available weeks list
  useEffect(() => {
    (async () => {
      try {
        setWeeksLoading(true);
        const data = await weeklyDigestApi.listWeeks();
        setWeeks(data.weeks || []);
      } catch {
        // Silent fail — weeks sidebar is non-critical
      } finally {
        setWeeksLoading(false);
      }
    })();
  }, []);

  // Fetch digest for a given week (or current)
  const fetchDigest = useCallback(async (weekKey?: string) => {
    try {
      setLoading(true);
      setError(null);
      let data: WeeklyDigest;
      if (weekKey) {
        data = await weeklyDigestApi.getByWeek(weekKey);
      } else {
        data = await weeklyDigestApi.getCurrent();
      }
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

  // Load current week's digest initially
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
      // Refresh weeks list
      const weeksData = await weeklyDigestApi.listWeeks();
      setWeeks(weeksData.weeks || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  // Parse JSON strings if backend returns them as strings
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const parseJson = <T,>(val: unknown, fallback: T): T => {
    if (typeof val === 'string') {
      try { return JSON.parse(val) as T; } catch { return fallback; }
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

  // Determine if this is the current week
  const getCurrentWeekKey = () => {
    const now = new Date();
    const janFirst = new Date(now.getFullYear(), 0, 1);
    const days = Math.floor((now.getTime() - janFirst.getTime()) / 86400000);
    const weekNum = Math.ceil((days + janFirst.getDay() + 1) / 7);
    return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
  };

  const isCurrentWeek = digest?.week_key === getCurrentWeekKey();

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left Sidebar — Week History */}
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
        <ReportSidebarHeader icon={ClipboardList} title="历史周刊" countText={`共 ${weeks.length} 期`} />

        {/* Current week button */}
        <div style={{ padding: '8px 12px 4px' }}>
          <CurrentPeriodButton
            active={isCurrentWeek || !selectedWeek}
            icon={Pin}
            onClick={() => fetchDigest()}
          >
            本周
          </CurrentPeriodButton>
        </div>

        {/* Weeks list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '4px 12px 12px',
        }}>
          {weeksLoading ? (
            <div style={{ padding: '20px 8px', textAlign: 'center', fontSize: 12, color: T.gray400 }}>
              加载中...
            </div>
          ) : weeks.length === 0 ? (
            <div style={{ padding: '20px 8px', textAlign: 'center', fontSize: 12, color: T.gray400 }}>
              暂无历史周刊
            </div>
          ) : (
            weeks.map((w) => {
              const isActive = selectedWeek === w.week_key;
              return (
                <button
                  key={w.week_key}
                  onClick={() => handleWeekSelect(w.week_key)}
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
                      {w.week_label}
                    </span>
                    <span style={{
                      fontSize: 9, fontWeight: 600,
                      color: w.status === 'DONE' ? T.teal : w.status === 'ERROR' ? T.red : T.gray400,
                      background: w.status === 'DONE' ? T.tealLight : w.status === 'ERROR' ? T.redLight : T.gray100,
                      padding: '1px 6px', borderRadius: 4,
                    }}>
                      {w.status === 'DONE' ? '已完成' : w.status === 'ERROR' ? '失败' : w.status === 'GENERATING' ? '生成中' : '待生成'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: T.gray400, marginTop: 2 }}>
                    {w.week_key}
                  </div>
                  {w.takeaway && (
                    <div style={{
                      fontSize: 11, color: T.gray400, marginTop: 3,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {w.takeaway}
                    </div>
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
              <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>AI 周刊</h1>
              <ReportBadge>WEEKLY DIGEST</ReportBadge>
              {!isCurrentWeek && digest && (
                <ReportBadge tone="history">历史回顾</ReportBadge>
              )}
            </div>
            <p style={{ fontSize: 13, color: T.gray400 }}>
              {digest ? `${digest.week_label}（${digest.week_start} ~ ${digest.week_end}）` : '加载中...'}
              {digest?.content_count ? ` · 基于 ${digest.content_count} 条内容分析` : ''}
            </p>
          </div>
          <ReportActionButton
            onClick={() => handleRegenerate(digest?.week_key)}
            loading={generating}
            icon={RefreshCw}
          >
            重新生成
          </ReportActionButton>
        </div>

        {loading ? (
          <ReportStatusPanel icon={ClipboardList}>正在加载周刊...</ReportStatusPanel>
        ) : error ? (
          <ReportStatusPanel icon={AlertTriangle} tone="error">{error}</ReportStatusPanel>
        ) : digest?.status === 'ERROR' ? (
          <div style={{ textAlign: 'center', padding: 80 }}>
            <AlertTriangle size={30} color={T.red} strokeWidth={1.9} style={{ marginBottom: 12 }} />
            <div style={{ color: T.gray500, fontSize: 14, marginBottom: 12 }}>{digest.overview}</div>
            <ReportActionButton
              onClick={() => handleRegenerate(digest.week_key)}
              loading={generating}
              icon={RefreshCw}
            >
              重试生成
            </ReportActionButton>
          </div>
        ) : digest?.status === 'GENERATING' || digest?.status === 'PENDING' ? (
          <ReportStatusPanel
            icon={Loader2}
            action={(
              <button
                onClick={() => fetchDigest(digest.week_key)}
                style={{
                  padding: '6px 16px', fontSize: 12, fontWeight: 500,
                  background: T.gray100, color: T.gray600,
                  border: 'none', borderRadius: T.radiusSm, cursor: 'pointer',
                }}
              >
                刷新状态
              </button>
            )}
          >
            周刊生成中，请稍候...
          </ReportStatusPanel>
        ) : digest ? (
          <div style={{ maxWidth: 860 }}>
            {/* Takeaway */}
            {digest.takeaway && (
              <div style={{
                background: `linear-gradient(135deg, ${T.purple}10, ${T.primary}10)`,
                borderRadius: T.radius, padding: '20px 24px',
                marginBottom: 24, borderLeft: `4px solid ${T.purple}`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: T.purple, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  本周要点
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, color: T.gray900, lineHeight: 1.6 }}>
                  {digest.takeaway}
                </div>
              </div>
            )}

            {/* Overview */}
            {digest.overview && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Newspaper} title="本周概述" />
                <p style={{ fontSize: 14, color: T.gray600, lineHeight: 1.8 }}>{digest.overview}</p>
              </div>
            )}

            {/* Keywords */}
            {(keywords || []).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={KeyRound} title="本周关键词" />
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
            {(trends || []).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={TrendingUp} title="内容趋势" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {trends.map((trend: TrendItem, i: number) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 12,
                      padding: '14px 18px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: trend.color || T.purple, marginTop: 5, flexShrink: 0,
                      }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, marginBottom: 2 }}>{trend.title}</div>
                        <div style={{ fontSize: 13, color: T.gray500 }}>{trend.desc}</div>
                      </div>
                      {trend.momentum && (
                        <span style={{
                          fontSize: 10, fontWeight: 600,
                          color: trend.momentum === 'up' ? T.teal : trend.momentum === 'down' ? T.red : T.gray500,
                          background: trend.momentum === 'up' ? T.tealLight : trend.momentum === 'down' ? T.redLight : T.gray100,
                          padding: '2px 8px', borderRadius: 4,
                        }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            {trend.momentum === 'up' ? (
                              <ArrowUp size={12} strokeWidth={2.2} />
                            ) : trend.momentum === 'down' ? (
                              <ArrowDown size={12} strokeWidth={2.2} />
                            ) : (
                              <ArrowRight size={12} strokeWidth={2.2} />
                            )}
                            {trend.momentum === 'up' ? '上升' : trend.momentum === 'down' ? '下降' : '平稳'}
                          </span>
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Topic Clusters */}
            {(topicClusters || []).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Flame} title="热门话题聚类" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
                  {topicClusters.map((cluster: ClusterItem, i: number) => (
                    <div key={i} style={{
                      padding: '14px 18px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900 }}>{cluster.name}</span>
                        <span style={{
                          fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: T.primary,
                          background: T.primaryLight, padding: '2px 8px', borderRadius: 10,
                        }}>
                          {cluster.count}篇
                        </span>
                      </div>
                      <div style={{ fontSize: 12, color: T.gray400, lineHeight: 1.5 }}>
                        代表: {cluster.representative_title}
                      </div>
                      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{
                          flex: 1, height: 4, borderRadius: 2, background: T.gray100,
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${Math.min(cluster.heat, 100)}%`,
                            height: '100%', borderRadius: 2,
                            background: `linear-gradient(90deg, ${T.primary}, ${T.purple})`,
                          }} />
                        </div>
                        <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
                          {cluster.heat}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top Picks */}
            {(topPicks || []).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Target} title="精选选题 TOP 5" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {topPicks.map((pick: PickItem, i: number) => (
                    <div key={i} style={{
                      padding: '16px 20px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{
                            fontSize: 11, fontWeight: 700, color: T.white,
                            background: i === 0 ? '#FF6B35' : i === 1 ? '#F59E0B' : i === 2 ? '#8B5CF6' : T.primary,
                            width: 22, height: 22, borderRadius: '50%',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}>
                            {i + 1}
                          </span>
                          <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900 }}>{pick.title}</span>
                        </div>
                        <div style={{ fontSize: 12, color: T.gray500, marginLeft: 30 }}>{pick.reason}</div>
                        <div style={{ display: 'flex', gap: 6, marginTop: 6, marginLeft: 30, alignItems: 'center' }}>
                          {pick.source && (
                            <span style={{ fontSize: 10, color: T.gray400 }}>
                              信源 {pick.source}
                            </span>
                          )}
                          {pick.category && (
                            <span style={{ fontSize: 10, color: T.teal, background: T.tealLight, padding: '1px 8px', borderRadius: 4 }}>
                              {pick.category}
                            </span>
                          )}
                          {(pick.platforms ?? []).length > 0 && (pick.platforms ?? []).map((p: string, j: number) => (
                            <span key={j} style={{
                              fontSize: 10, color: T.teal, background: T.tealLight,
                              padding: '1px 8px', borderRadius: 4,
                            }}>
                              {p}
                            </span>
                          ))}
                        </div>
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
                  ))}
                </div>
              </div>
            )}

            {/* Category Summary */}
            {categorySummary && typeof categorySummary === 'object' && Object.keys(categorySummary).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={BarChart3} title="分类概览" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                  {Object.entries(categorySummary || {}).map(([cat, info]) => {
                    return (
                    <div key={cat} style={{
                      padding: '14px 18px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900 }}>{cat}</span>
                        <span style={{ fontSize: 12, fontFamily: T.mono, color: T.gray400 }}>
                          {info.count}篇
                        </span>
                      </div>
                      <div style={{ fontSize: 12, color: T.gray500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {info.top_title || '-'}
                      </div>
                      {info.avg_score !== undefined && (
                        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{
                            flex: 1, height: 4, borderRadius: 2, background: T.gray100,
                            overflow: 'hidden',
                          }}>
                            <div style={{
                              width: `${Math.min(info.avg_score, 100)}%`,
                              height: '100%', borderRadius: 2,
                              background: T.teal,
                            }} />
                          </div>
                          <span style={{ fontSize: 10, color: T.gray400, fontFamily: T.mono }}>
                            {info.avg_score.toFixed(0)}
                          </span>
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Action Items */}
            {(actionItems || []).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={CheckCircle2} title="下周创作行动清单" />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {actionItems.map((item: ActionItem, i: number) => (
                    <div key={i} style={{
                      padding: '14px 18px', background: T.white,
                      borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                      display: 'flex', alignItems: 'flex-start', gap: 12,
                    }}>
                      <div style={{
                        width: 24, height: 24, borderRadius: '50%',
                        background: i < 3 ? T.primaryLight : T.gray100,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 700,
                        color: i < 3 ? T.primary : T.gray500,
                        flexShrink: 0, marginTop: 1,
                      }}>
                        {i + 1}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, marginBottom: 4 }}>
                          {item.title}
                        </div>
                        <div style={{ fontSize: 12, color: T.gray500, lineHeight: 1.5, marginBottom: 6 }}>
                          {item.angle}
                        </div>
                        <div style={{ display: 'flex', gap: 6 }}>
                          {item.platform && (
                            <span style={{ fontSize: 10, color: T.teal, background: T.tealLight, padding: '1px 8px', borderRadius: 4 }}>
                              {item.platform}
                            </span>
                          )}
                          {item.difficulty && (
                            <span style={{
                              fontSize: 10, fontWeight: 500,
                              color: item.difficulty === '简单' ? T.teal : item.difficulty === '中等' ? T.amber : T.red,
                              background: item.difficulty === '简单' ? T.tealLight : item.difficulty === '中等' ? T.amberLight : T.redLight,
                              padding: '1px 8px', borderRadius: 4,
                            }}>
                              {item.difficulty}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Platform Tips */}
            {platformTips && typeof platformTips === 'object' && Object.keys(platformTips).length > 0 && (
              <div style={{ marginBottom: 28 }}>
                <ReportSectionTitle icon={Lightbulb} title="平台创作建议" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
                  {Object.entries(platformTips || {}).map(([platform, tips]) => (
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
              flexWrap: 'wrap',
            }}>
              <ReportFooterStat icon={CalendarDays}>{digest.week_label}</ReportFooterStat>
              <ReportFooterStat icon={BarChart3}>分析 {digest.analyzed_count} 条内容</ReportFooterStat>
              <ReportFooterStat icon={RadioTower}>来自 {digest.source_count} 个信源</ReportFooterStat>
              <ReportFooterStat icon={Folder}>覆盖 {digest.category_count} 个分类</ReportFooterStat>
            </div>
          </div>
        ) : (
          <ReportStatusPanel icon={Inbox}>
            暂无周刊数据
          </ReportStatusPanel>
        )}
      </div>
    </div>
  );
}
