'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { T, LEVEL_CONFIG } from '@/lib/design-tokens';
import { useAppContext } from '@/components/ClientLayout';
import LevelBadge from '@/components/LevelBadge';
import PlatformTag from '@/components/PlatformTag';
import { contentsApi, analysesApi, creationApi } from '@/lib/api';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';
import { getRecommendLevel } from '@/types';

// ── Helpers ──

function timeAgo(dateStr: string): string {
  try {
    const now = Date.now();
    const then = new Date(dateStr).getTime();
    const diffSec = Math.floor((now - then) / 1000);
    if (diffSec < 60) return '刚刚';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} 天前`;
    return new Date(dateStr).toLocaleDateString('zh-CN');
  } catch {
    return '';
  }
}

function extractRiskNotes(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.risk_notes) return [];
  if (typeof analysis.risk_notes === 'string') {
    return analysis.risk_notes ? [analysis.risk_notes] : [];
  }
  if (Array.isArray(analysis.risk_notes)) {
    return analysis.risk_notes.filter((n: unknown) => typeof n === 'string' && n.length > 0);
  }
  if (typeof analysis.risk_notes === 'object') {
    const obj = analysis.risk_notes as Record<string, unknown>;
    const notes: string[] = [];
    for (const v of Object.values(obj)) {
      if (typeof v === 'string' && v.length > 0) notes.push(v);
      if (Array.isArray(v)) {
        for (const item of v) {
          if (typeof item === 'string' && item.length > 0) notes.push(item);
        }
      }
    }
    return notes;
  }
  return [];
}

function extractCreatorAngles(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.creator_angles) return [];
  if (Array.isArray(analysis.creator_angles)) {
    return analysis.creator_angles.filter((a: unknown) => typeof a === 'string');
  }
  return [];
}

function extractTags(item: ContentItem, analysis: ContentAnalysis | null): string[] {
  const tags: string[] = [];
  if (item.tags && Array.isArray(item.tags)) {
    tags.push(...item.tags);
  }
  if (analysis?.tags && Array.isArray(analysis.tags)) {
    for (const t of analysis.tags) {
      if (!tags.includes(t)) tags.push(t);
    }
  }
  return tags;
}

function extractTitleSuggestions(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.title_suggestions) return [];
  if (Array.isArray(analysis.title_suggestions)) {
    return analysis.title_suggestions.filter((t: unknown) => typeof t === 'string');
  }
  return [];
}

function extractKeyPoints(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.key_points) return [];
  if (Array.isArray(analysis.key_points)) {
    return analysis.key_points.filter((p: unknown) => typeof p === 'string');
  }
  return [];
}

// ── Sub-components ──

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontSize: 14,
        fontWeight: 600,
        color: T.gray800,
        marginBottom: 14,
        paddingBottom: 8,
        borderBottom: `2px solid ${T.gray100}`,
        letterSpacing: '0.02em',
      }}
    >
      {children}
    </h3>
  );
}

function ScoreCard({ label, value, desc, isRisk }: { label: string; value: number; desc: string; isRisk?: boolean }) {
  const color = isRisk
    ? value > 70
      ? T.red
      : value > 50
        ? T.amber
        : T.teal
    : value >= 80
      ? T.primary
      : value >= 60
        ? T.teal
        : T.gray400;

  return (
    <div style={{ textAlign: 'center' }}>
      <div
        style={{
          fontSize: 32,
          fontWeight: 700,
          fontFamily: T.mono,
          color,
          lineHeight: 1,
        }}
      >
        {Math.round(value)}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: T.gray700, marginTop: 6 }}>{label}</div>
      <div style={{ fontSize: 11, color: T.gray400, marginTop: 2 }}>{desc}</div>
    </div>
  );
}

// ── Creation plan type ──

interface CreationPlan {
  platform: string;
  titles?: string[];
  cover_text?: string;
  structure?: string;
  tags?: string[];
  style?: string;
  [key: string]: unknown;
}

// ── Page Component ──

export default function TopicDetailPage() {
  const router = useRouter();
  const params = useParams();
  const { favorites, toggleFavorite } = useAppContext();

  const [item, setItem] = useState<ContentItem | null>(null);
  const [analysis, setAnalysis] = useState<ContentAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creationPlan, setCreationPlan] = useState<CreationPlan | null>(null);
  const [creating, setCreating] = useState(false);
  const [creatingPlatform, setCreatingPlatform] = useState<string | null>(null);
  const [creationError, setCreationError] = useState<string | null>(null);

  const contentId = Number(params.id);

  // Fetch content + analysis
  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError(null);

      try {
        // Fetch content detail
        const content = await contentsApi.get(contentId);
        if (cancelled) return;
        setItem(content);

        // If analysis is embedded, use it directly
        if (content.analysis) {
          setAnalysis(content.analysis);
        } else {
          // Try to fetch analysis separately
          try {
            const a = await analysesApi.getAnalysis(contentId);
            if (!cancelled) setAnalysis(a);
          } catch {
            // No analysis yet — that's okay, show content without analysis
          }
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : '加载失败';
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    if (contentId && !isNaN(contentId)) {
      fetchData();
    }

    return () => { cancelled = true; };
  }, [contentId]);

  // Handlers
  const isFav = item ? favorites.has(item.id) : false;

  const handleToggleFavorite = async () => {
    if (!item) return;
    try {
      const res = await contentsApi.toggleFavorite(item.id);
      // The context will sync on next refresh, but we update locally too
      toggleFavorite(item.id);
      setItem(prev => prev ? { ...prev, is_favorited: res.is_favorited } : prev);
    } catch {
      // Silently fail
    }
  };

  const handleGeneratePlan = async (platform: string) => {
    if (!contentId) return;
    setCreating(true);
    setCreatingPlatform(platform);
    setCreationError(null);

    try {
      const result = await creationApi.generatePlan(contentId, platform);
      setCreationPlan(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '生成失败';
      setCreationError(msg);
    } finally {
      setCreating(false);
      setCreatingPlatform(null);
    }
  };

  // ── Render: Loading ──
  if (loading) {
    return (
      <div style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
        <div style={{ maxWidth: 760 }}>
          {/* Skeleton */}
          <div style={{ background: T.white, borderRadius: T.radius, padding: 32, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
            <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
              <div style={{ width: 80, height: 24, background: T.gray100, borderRadius: 20 }} />
              <div style={{ width: 48, height: 24, background: T.gray100, borderRadius: 4 }} />
            </div>
            <div style={{ height: 28, background: T.gray100, borderRadius: 6, marginBottom: 12, width: '80%' }} />
            <div style={{ height: 28, background: T.gray100, borderRadius: 6, marginBottom: 12, width: '60%' }} />
            <div style={{ display: 'flex', gap: 16 }}>
              <div style={{ width: 60, height: 16, background: T.gray100, borderRadius: 4 }} />
              <div style={{ width: 80, height: 16, background: T.gray100, borderRadius: 4 }} />
            </div>
          </div>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ background: T.white, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
              <div style={{ height: 16, background: T.gray100, borderRadius: 4, width: '30%', marginBottom: 16 }} />
              <div style={{ height: 14, background: T.gray50, borderRadius: 4, width: '100%', marginBottom: 8 }} />
              <div style={{ height: 14, background: T.gray50, borderRadius: 4, width: '90%', marginBottom: 8 }} />
              <div style={{ height: 14, background: T.gray50, borderRadius: 4, width: '75%' }} />
            </div>
          ))}
          <div style={{ textAlign: 'center', color: T.gray400, fontSize: 13, marginTop: 20 }}>
            加载中...
          </div>
        </div>
      </div>
    );
  }

  // ── Render: Error ──
  if (error || !item) {
    return (
      <div style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
        <div style={{ maxWidth: 760 }}>
          <button
            onClick={() => router.push('/')}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              color: T.gray500,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              marginBottom: 24,
              padding: '4px 0',
            }}
          >
            <span style={{ fontSize: 16 }}>←</span> 返回
          </button>
          <div
            style={{
              background: T.redLight,
              borderRadius: T.radius,
              padding: 32,
              textAlign: 'center',
              border: '1px solid #FECACA',
            }}
          >
            <div style={{ fontSize: 40, marginBottom: 12 }}>😕</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: T.gray800, marginBottom: 8 }}>
              内容加载失败
            </div>
            <div style={{ fontSize: 14, color: T.gray500, marginBottom: 20 }}>
              {error || '未找到该内容'}
            </div>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 20px',
                fontSize: 13,
                fontWeight: 500,
                background: T.white,
                color: T.gray700,
                border: `1px solid ${T.gray200}`,
                borderRadius: T.radiusSm,
                cursor: 'pointer',
              }}
            >
              重新加载
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Derived data ──
  const tags = extractTags(item, analysis);
  const level: RecommendLevel = analysis ? getRecommendLevel(analysis) : '不建议追';
  const levelCfg = LEVEL_CONFIG[level] || LEVEL_CONFIG['不建议追'];
  const angles = extractCreatorAngles(analysis);
  const riskNotes = extractRiskNotes(analysis);
  const titleSuggestions = extractTitleSuggestions(analysis);
  const keyPoints = extractKeyPoints(analysis);

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Back */}
      <button
        onClick={() => router.push('/')}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 13,
          color: T.gray500,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          marginBottom: 24,
          padding: '4px 0',
        }}
      >
        <span style={{ fontSize: 16 }}>←</span> 返回今日选题
      </button>

      <div style={{ maxWidth: 760 }}>
        {/* Title Block */}
        <div
          style={{
            background: T.white,
            borderRadius: T.radius,
            padding: 32,
            marginBottom: 20,
            border: `1px solid ${T.gray100}`,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: 16,
              flexWrap: 'wrap',
            }}
          >
            <LevelBadge level={level} />
            {tags.map((c) => (
              <span
                key={c}
                style={{
                  fontSize: 12,
                  color: T.gray500,
                  fontWeight: 500,
                  background: T.gray100,
                  padding: '2px 8px',
                  borderRadius: 4,
                }}
              >
                {c}
              </span>
            ))}
          </div>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 700,
              lineHeight: 1.5,
              color: T.gray900,
              marginBottom: 12,
            }}
          >
            {item.title}
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13, color: T.gray400, flexWrap: 'wrap' }}>
            {item.source_name && (
              <span>
                <b style={{ color: T.gray600 }}>{item.source_name}</b>
              </span>
            )}
            {item.published_at && <span>{timeAgo(item.published_at)}</span>}
            <span style={{ color: T.gray300 }}>|</span>
            {item.source_type && <span>{item.source_type}</span>}
            {item.author && (
              <>
                <span style={{ color: T.gray300 }}>|</span>
                <span>{item.author}</span>
              </>
            )}
          </div>

          {/* Action bar */}
          <div style={{ marginTop: 20, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button
              onClick={handleToggleFavorite}
              style={{
                padding: '8px 20px',
                fontSize: 13,
                fontWeight: 500,
                background: isFav ? T.primaryLight : T.gray100,
                color: isFav ? T.primary : T.gray600,
                border: `1px solid ${isFav ? T.primaryBorder : T.gray200}`,
                borderRadius: T.radiusSm,
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {isFav ? '★ 已收藏' : '☆ 收藏选题'}
            </button>

            {item.url && (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  padding: '8px 20px',
                  fontSize: 13,
                  fontWeight: 500,
                  background: T.tealLight,
                  color: T.teal,
                  border: `1px solid ${T.tealBorder}`,
                  borderRadius: T.radiusSm,
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  transition: 'all 0.15s',
                }}
              >
                查看原文 ↗
              </a>
            )}
          </div>
        </div>

        {/* Scores */}
        {analysis && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>评分概览</SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
              <ScoreCard label="热度分" value={analysis.hot_score ?? 0} desc="当前传播热度" />
              <ScoreCard label="创作价值" value={analysis.creator_score ?? 0} desc="值得创作的程度" />
              <ScoreCard label="风险分" value={analysis.risk_score ?? 0} desc="内容风险等级" isRisk />
            </div>

            {/* Curation score bar */}
            {analysis.curation_score != null && analysis.curation_score > 0 && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${T.gray100}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 500, color: T.gray500 }}>精选评分</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.primary, fontFamily: T.mono }}>
                    {Math.round(analysis.curation_score)} 分
                  </span>
                </div>
                <div style={{ height: 6, background: T.gray100, borderRadius: 3, overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(100, analysis.curation_score)}%`,
                      background: `linear-gradient(90deg, ${T.primary}, #FF8F65)`,
                      borderRadius: 3,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* AI Summary */}
        {analysis?.summary && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>AI 摘要</SectionTitle>
            <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray600 }}>{analysis.summary}</p>
          </div>
        )}

        {/* Key Points */}
        {keyPoints.length > 0 && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>核心要点</SectionTitle>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8, padding: 0, margin: 0 }}>
              {keyPoints.map((point, i) => (
                <li
                  key={i}
                  style={{
                    fontSize: 14,
                    lineHeight: 1.6,
                    color: T.gray700,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 8,
                  }}
                >
                  <span style={{ color: T.primary, fontWeight: 700, flexShrink: 0 }}>•</span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendation Reason */}
        {analysis?.recommended_reason && (
          <div
            style={{
              background: levelCfg.bg,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${levelCfg.border}`,
            }}
          >
            <SectionTitle>推荐理由</SectionTitle>
            <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray700 }}>{analysis.recommended_reason}</p>
          </div>
        )}

        {/* Creator Angles */}
        {angles.length > 0 && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>可切入角度</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {angles.map((angle, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    gap: 12,
                    alignItems: 'flex-start',
                    padding: '12px 16px',
                    background: T.gray50,
                    borderRadius: T.radiusSm,
                  }}
                >
                  <span
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      background: `linear-gradient(135deg, ${T.primary}, #FF8F65)`,
                      color: T.white,
                      fontSize: 11,
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: 1,
                    }}
                  >
                    {i + 1}
                  </span>
                  <span style={{ fontSize: 14, lineHeight: 1.6, color: T.gray700 }}>{angle}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Title Suggestions */}
        {titleSuggestions.length > 0 && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>备选标题建议</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {titleSuggestions.map((title, i) => (
                <div
                  key={i}
                  style={{
                    padding: '10px 14px',
                    background: T.gray50,
                    borderRadius: T.radiusSm,
                    fontSize: 14,
                    lineHeight: 1.5,
                    color: T.gray700,
                    borderLeft: `3px solid ${T.primary}`,
                  }}
                >
                  {title}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Risk Notes */}
        {riskNotes.length > 0 && (
          <div
            style={{
              background: T.redLight,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: '1px solid #FECACA',
            }}
          >
            <SectionTitle>风险提示</SectionTitle>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {riskNotes.map((note, i) => (
                <li
                  key={i}
                  style={{
                    fontSize: 13,
                    lineHeight: 1.6,
                    color: '#991B1B',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 8,
                  }}
                >
                  <span style={{ color: T.red, fontWeight: 700, flexShrink: 0 }}>!</span>
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Creation Plan Generator */}
        {analysis && (
          <div
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.gray100}`,
            }}
          >
            <SectionTitle>✍️ 生成创作方案</SectionTitle>
            <p style={{ fontSize: 13, color: T.gray500, marginBottom: 16 }}>
              选择平台，AI 将基于此内容生成完整的创作方案
            </p>

            {/* Platform buttons */}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {[
                { id: 'xiaohongshu', name: '小红书', icon: '📕' },
                { id: 'wechat', name: '公众号', icon: '📝' },
                { id: 'short_video', name: '短视频', icon: '🎬' },
              ].map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleGeneratePlan(p.id)}
                  disabled={creating}
                  style={{
                    padding: '10px 18px',
                    fontSize: 13,
                    fontWeight: 500,
                    background: creatingPlatform === p.id ? T.primaryLight : T.gray50,
                    color: creatingPlatform === p.id ? T.primary : T.gray700,
                    border: `1px solid ${creatingPlatform === p.id ? T.primaryBorder : T.gray200}`,
                    borderRadius: T.radiusSm,
                    cursor: creating ? 'wait' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    transition: 'all 0.15s',
                    opacity: creating && creatingPlatform !== p.id ? 0.5 : 1,
                  }}
                >
                  <span>{p.icon}</span>
                  {creatingPlatform === p.id ? '生成中...' : p.name}
                </button>
              ))}
            </div>

            {/* Creation error */}
            {creationError && (
              <div
                style={{
                  marginTop: 12,
                  padding: '10px 14px',
                  background: T.redLight,
                  borderRadius: T.radiusSm,
                  fontSize: 13,
                  color: '#991B1B',
                }}
              >
                生成失败：{creationError}
              </div>
            )}

            {/* Creation plan result */}
            {creationPlan && (
              <div
                style={{
                  marginTop: 16,
                  padding: 20,
                  background: T.gray50,
                  borderRadius: T.radiusSm,
                  border: `1px solid ${T.gray100}`,
                }}
              >
                <div style={{ fontSize: 14, fontWeight: 600, color: T.gray800, marginBottom: 12 }}>
                  创作方案
                </div>

                {/* Render plan fields dynamically */}
                {creationPlan.titles && Array.isArray(creationPlan.titles) && creationPlan.titles.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: T.gray600, marginBottom: 6 }}>备选标题</div>
                    {creationPlan.titles.map((t: string, i: number) => (
                      <div key={i} style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6, paddingLeft: 8, borderLeft: `2px solid ${T.primary}`, marginBottom: 4 }}>
                        {t}
                      </div>
                    ))}
                  </div>
                )}

                {creationPlan.cover_text && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: T.gray600, marginBottom: 6 }}>封面文案</div>
                    <div style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6 }}>{String(creationPlan.cover_text)}</div>
                  </div>
                )}

                {creationPlan.structure && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: T.gray600, marginBottom: 6 }}>正文结构</div>
                    <div style={{ fontSize: 13, color: T.gray700, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>{String(creationPlan.structure)}</div>
                  </div>
                )}

                {creationPlan.tags && Array.isArray(creationPlan.tags) && creationPlan.tags.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: T.gray600, marginBottom: 6 }}>推荐标签</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {creationPlan.tags.map((t: string, i: number) => (
                        <span key={i} style={{ fontSize: 12, padding: '2px 8px', background: T.primaryLight, color: T.primary, borderRadius: 4 }}>
                          #{t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {creationPlan.style && (
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: T.gray600, marginBottom: 6 }}>风格建议</div>
                    <div style={{ fontSize: 13, color: T.gray700, lineHeight: 1.6 }}>{String(creationPlan.style)}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* No analysis hint */}
        {!analysis && (
          <div
            style={{
              background: T.amberLight,
              borderRadius: T.radius,
              padding: 28,
              marginBottom: 20,
              border: `1px solid ${T.amberBorder}`,
            }}
          >
            <SectionTitle>AI 分析</SectionTitle>
            <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray600 }}>
              该内容尚未完成 AI 分析。评分、摘要和创作建议将在分析完成后显示。
            </p>
          </div>
        )}

        {/* Spacer at bottom */}
        <div style={{ height: 40 }} />
      </div>
    </div>
  );
}
