'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { AlertTriangle } from 'lucide-react';
import { T, LEVEL_CONFIG } from '@/lib/design-tokens';
import { useAppContext } from '@/components/ClientLayout';
import { contentsApi, analysesApi } from '@/lib/api';
import type { ContentItem, ContentAnalysis, RecommendLevel } from '@/types';
import { getRecommendLevel } from '@/types';
import { timeAgo, extractTags, extractCreatorAngles, extractRiskNotes, extractTitleSuggestions, extractKeyPoints } from '@/lib/utils';
import SectionTitle from '@/components/SectionTitle';
import ScoreCard from '@/components/ScoreCard';
import TopicHeaderCard from '@/components/TopicHeaderCard';
import TopicCreationGenerator from '@/components/TopicCreationGenerator';

// ── Page Component ──

export default function TopicDetailPage() {
  const router = useRouter();
  const params = useParams();
  const { favorites, toggleFavorite } = useAppContext();

  const [item, setItem] = useState<ContentItem | null>(null);
  const [analysis, setAnalysis] = useState<ContentAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const contentId = Number(params.id);

  // Fetch content + analysis
  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      setError(null);

      try {
        const content = await contentsApi.get(contentId);
        if (cancelled) return;
        setItem(content);

        if (content.analysis) {
          setAnalysis(content.analysis);
        } else {
          try {
            const a = await analysesApi.getAnalysis(contentId);
            if (!cancelled) setAnalysis(a);
          } catch {
            // No analysis yet
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
      toggleFavorite(item.id);
      setItem(prev => prev ? { ...prev, is_favorited: res.is_favorited } : prev);
    } catch {
      // Silently fail
    }
  };

  // ── Render: Loading ──
  if (loading) {
    return (
      <div style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
        <div style={{ maxWidth: 760 }}>
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
              background: 'none', border: 'none', cursor: 'pointer', fontSize: 13,
              color: T.gray500, display: 'flex', alignItems: 'center', gap: 4,
              marginBottom: 24, padding: '4px 0',
            }}
          >
            <span style={{ fontSize: 16 }}>←</span> 返回
          </button>
          <div
            style={{
              background: T.redLight, borderRadius: T.radius, padding: 32,
              textAlign: 'center', border: '1px solid #FECACA',
            }}
          >
            <AlertTriangle size={34} color={T.red} strokeWidth={1.9} style={{ marginBottom: 12 }} />
            <div style={{ fontSize: 16, fontWeight: 600, color: T.gray800, marginBottom: 8 }}>
              内容加载失败
            </div>
            <div style={{ fontSize: 14, color: T.gray500, marginBottom: 20 }}>
              {error || '未找到该内容'}
            </div>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 20px', fontSize: 13, fontWeight: 500,
                background: T.white, color: T.gray700, border: `1px solid ${T.gray200}`,
                borderRadius: T.radiusSm, cursor: 'pointer',
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
          background: 'none', border: 'none', cursor: 'pointer', fontSize: 13,
          color: T.gray500, display: 'flex', alignItems: 'center', gap: 4,
          marginBottom: 24, padding: '4px 0',
        }}
      >
        <span style={{ fontSize: 16 }}>←</span> 返回今日选题
      </button>

      <div style={{ maxWidth: 760 }}>
        {/* Header Card */}
        <TopicHeaderCard
          item={item}
          analysis={analysis}
          level={level}
          tags={tags}
          isFav={isFav}
          onToggleFavorite={handleToggleFavorite}
          timeAgoStr={item.published_at ? timeAgo(item.published_at) : ''}
        />

        {/* Scores */}
        {analysis && (
          <div
            style={{
              background: T.white, borderRadius: T.radius, padding: 28,
              marginBottom: 20, border: `1px solid ${T.gray100}`,
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
          <div style={{ background: T.white, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
            <SectionTitle>AI 摘要</SectionTitle>
            <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray600 }}>{analysis.summary}</p>
          </div>
        )}

        {/* Key Points */}
        {keyPoints.length > 0 && (
          <div style={{ background: T.white, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
            <SectionTitle>核心要点</SectionTitle>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8, padding: 0, margin: 0 }}>
              {keyPoints.map((point, i) => (
                <li key={i} style={{ fontSize: 14, lineHeight: 1.6, color: T.gray700, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ color: T.primary, fontWeight: 700, flexShrink: 0 }}>•</span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendation Reason */}
        {analysis?.recommended_reason && (
          <div style={{ background: levelCfg.bg, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${levelCfg.border}` }}>
            <SectionTitle>推荐理由</SectionTitle>
            <p style={{ fontSize: 14, lineHeight: 1.8, color: T.gray700 }}>{analysis.recommended_reason}</p>
          </div>
        )}

        {/* Creator Angles */}
        {angles.length > 0 && (
          <div style={{ background: T.white, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
            <SectionTitle>可切入角度</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {angles.map((angle, i) => (
                <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '12px 16px', background: T.gray50, borderRadius: T.radiusSm }}>
                  <span
                    style={{
                      width: 22, height: 22, borderRadius: '50%',
                      background: `linear-gradient(135deg, ${T.primary}, #FF8F65)`,
                      color: T.white, fontSize: 11, fontWeight: 600,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0, marginTop: 1,
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
          <div style={{ background: T.white, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.gray100}` }}>
            <SectionTitle>备选标题建议</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {titleSuggestions.map((title, i) => (
                <div key={i} style={{ padding: '10px 14px', background: T.gray50, borderRadius: T.radiusSm, fontSize: 14, lineHeight: 1.5, color: T.gray700, borderLeft: `3px solid ${T.primary}` }}>
                  {title}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Risk Notes */}
        {riskNotes.length > 0 && (
          <div style={{ background: T.redLight, borderRadius: T.radius, padding: 28, marginBottom: 20, border: '1px solid #FECACA' }}>
            <SectionTitle>风险提示</SectionTitle>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {riskNotes.map((note, i) => (
                <li key={i} style={{ fontSize: 13, lineHeight: 1.6, color: '#991B1B', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ color: T.red, fontWeight: 700, flexShrink: 0 }}>!</span>
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Creation Plan Generator */}
        {analysis && <TopicCreationGenerator contentId={contentId} />}

        {/* No analysis hint */}
        {!analysis && (
          <div style={{ background: T.amberLight, borderRadius: T.radius, padding: 28, marginBottom: 20, border: `1px solid ${T.amberBorder}` }}>
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
