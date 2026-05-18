'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { T } from '@/lib/design-tokens';
import { dailyReportApi } from '@/lib/api';

interface DailyReportData {
  id: number;
  report_date: string;
  weekday: string;
  overview: string | null;
  takeaway: string | null;
  keywords: string[] | null;
  trends: Array<{ title: string; desc: string; color: string }> | null;
  top_picks: Array<{ title: string; reason: string; score: number; platforms: string[] }> | null;
  platform_tips: Record<string, string[]> | null;
  topic_count: number;
  content_count: number;
  analyzed_count: number;
  status: string;
}

export default function DailyReportPage() {
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await dailyReportApi.getToday();
      setReport(data as DailyReportData);
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handleRegenerate = async () => {
    try {
      setGenerating(true);
      const data = await dailyReportApi.regenerate();
      setReport(data as DailyReportData);
    } catch (err: any) {
      setError(err.message || '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  // Parse JSON strings if needed
  const parseJson = (val: any) => {
    if (typeof val === 'string') {
      try { return JSON.parse(val); } catch { return null; }
    }
    return val;
  };

  const keywords = parseJson(report?.keywords);
  const trends = parseJson(report?.trends);
  const topPicks = parseJson(report?.top_picks);
  const platformTips = parseJson(report?.platform_tips);

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900 }}>AI 日报</h1>
            <span style={{
              fontSize: 10, fontWeight: 700, color: T.white,
              background: 'linear-gradient(135deg, #3B82F6, #8B5CF6)',
              padding: '3px 10px', borderRadius: 20,
            }}>
              AI GENERATED
            </span>
          </div>
          <p style={{ fontSize: 13, color: T.gray400 }}>
            {report ? `${report.report_date} ${report.weekday}` : '加载中...'}
            {report?.content_count ? ` · 基于 ${report.content_count} 条内容分析` : ''}
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={generating}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 500,
            background: generating ? T.gray100 : T.primary,
            color: generating ? T.gray400 : T.white,
            border: 'none', borderRadius: T.radiusSm,
            cursor: generating ? 'wait' : 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {generating ? '生成中...' : '🔄 重新生成'}
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📝</div>
          正在加载 AI 日报...
        </div>
      ) : error ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.red, fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
          {error}
        </div>
      ) : report?.status === 'ERROR' ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
          <div style={{ color: T.gray500, fontSize: 14, marginBottom: 12 }}>{report.overview}</div>
          <button
            onClick={handleRegenerate}
            style={{
              padding: '8px 20px', fontSize: 13, fontWeight: 500,
              background: T.primary, color: T.white,
              border: 'none', borderRadius: T.radiusSm, cursor: 'pointer',
            }}
          >
            重试生成
          </button>
        </div>
      ) : report?.status === 'GENERATING' ? (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
          AI 正在生成日报，请稍候...
        </div>
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
              <SectionTitle icon="📰" title="今日概述" />
              <p style={{ fontSize: 14, color: T.gray600, lineHeight: 1.8 }}>{report.overview}</p>
            </div>
          )}

          {/* Keywords */}
          {keywords?.length > 0 && (
            <div style={{ marginBottom: 28 }}>
              <SectionTitle icon="🔑" title="今日关键词" />
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
              <SectionTitle icon="📈" title="内容趋势" />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {trends.map((trend: any, i: number) => (
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
              <SectionTitle icon="🎯" title="精选选题推荐" />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {topPicks.map((pick: any, i: number) => (
                  <div key={i} style={{
                    padding: '16px 20px', background: T.white,
                    borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{
                          fontSize: 11, fontWeight: 700, color: T.white,
                          background: i === 0 ? '#FF6B35' : i === 1 ? '#F59E0B' : T.primary,
                          width: 22, height: 22, borderRadius: '50%',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          {i + 1}
                        </span>
                        <span style={{ fontSize: 14, fontWeight: 600, color: T.gray900 }}>{pick.title}</span>
                      </div>
                      <div style={{ fontSize: 12, color: T.gray500, marginLeft: 30 }}>{pick.reason}</div>
                      {pick.platforms?.length > 0 && (
                        <div style={{ display: 'flex', gap: 6, marginTop: 6, marginLeft: 30 }}>
                          {pick.platforms.map((p: string, j: number) => (
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
                ))}
              </div>
            </div>
          )}

          {/* Platform Tips */}
          {platformTips && typeof platformTips === 'object' && (
            <div style={{ marginBottom: 40 }}>
              <SectionTitle icon="💡" title="平台创作建议" />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
                {Object.entries(platformTips).map(([platform, tips]: [string, any]) => (
                  <div key={platform} style={{
                    padding: '16px 20px', background: T.white,
                    borderRadius: T.radiusSm, border: `1px solid ${T.gray100}`,
                  }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: T.gray900, marginBottom: 10 }}>
                      📱 {platform}
                    </div>
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
            <span>📅 {report.report_date} {report.weekday}</span>
            <span>📊 分析 {report.analyzed_count} 条内容</span>
            <span>🎯 推荐 {report.topic_count} 个选题</span>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 80, color: T.gray400, fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
          暂无日报数据
        </div>
      )}
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: string; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
      <span style={{ fontSize: 16 }}>{icon}</span>
      <h2 style={{ fontSize: 16, fontWeight: 700, color: T.gray900 }}>{title}</h2>
    </div>
  );
}
