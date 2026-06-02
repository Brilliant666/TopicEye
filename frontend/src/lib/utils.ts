/**
 * TopicEye Shared Utilities
 * Pure functions used across multiple pages
 */

import type { ContentItem, ContentAnalysis } from '@/types';
import { explainRecommendation } from '@/lib/recommendation';

// ─── timeAgo ───

export function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '从未同步';
  try {
    // Backend stores UTC datetimes without 'Z' suffix — append it so JS parses as UTC
    const normalized = dateStr.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(dateStr)
      ? dateStr
      : dateStr + 'Z';
    const date = new Date(normalized);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const seconds = Math.floor(diffMs / 1000);
    if (seconds < 60) return '刚刚';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} 分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} 小时前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} 天前`;
    const months = Math.floor(days / 30);
    return `${months} 个月前`;
  } catch {
    return '';
  }
}

// ─── weightStars ───

export const weightStars = (w: number) =>
  '●'.repeat(Math.min(w, 5)) + '○'.repeat(Math.max(5 - w, 0));

// ─── Analysis extract helpers (topics/[id] page) ───

export function extractRiskNotes(analysis: ContentAnalysis | null): string[] {
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

export function extractCreatorAngles(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.creator_angles) return [];
  if (Array.isArray(analysis.creator_angles)) {
    return analysis.creator_angles.filter((a: unknown) => typeof a === 'string');
  }
  return [];
}

export function extractTags(item: ContentItem, analysis: ContentAnalysis | null): string[] {
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

export function extractTitleSuggestions(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.title_suggestions) return [];
  if (Array.isArray(analysis.title_suggestions)) {
    return analysis.title_suggestions.filter((t: unknown) => typeof t === 'string');
  }
  return [];
}

export function extractKeyPoints(analysis: ContentAnalysis | null): string[] {
  if (!analysis?.key_points) return [];
  if (Array.isArray(analysis.key_points)) {
    return analysis.key_points.filter((p: unknown) => typeof p === 'string');
  }
  return [];
}

// ─── Tag color helper (today-picks) ───

import { T } from '@/lib/design-tokens';

const TAG_COLORS: Record<string, string> = {
  '模型': '#8B5CF6', '产品': '#3B82F6', '行业': '#10B981',
  '论文': '#6366F1', '技巧': '#F59E0B', '开源': '#EF4444',
  '工具': '#EC4899', '趋势': '#14B8A6', '大佬': '#F97316',
  '智能体': '#06B6D4', '具身智能': '#84CC16', '编码': '#A855F7',
};

export function getTagColor(tag: string): string {
  return TAG_COLORS[tag] || T.gray400;
}

// ─── Recommend level label (today-picks) ───

export function getRecommendLevelLabel(analysis: ContentAnalysis): string {
  return explainRecommendation(analysis).level;
}

// ─── Creation plan formatter ───

export function formatPlanText(plan: Record<string, unknown>): string {
  const lines: string[] = [];
  const p = plan as Record<string, unknown>;
  const titles = p.titles as string[] | undefined;
  if (titles) {
    lines.push('【备选标题】');
    titles.forEach((t: string, i: number) => lines.push(`${i + 1}. ${t}`));
    lines.push('');
  }
  const coverSlogan = p.cover_slogan as string | undefined;
  if (coverSlogan) lines.push(`封面文案：${coverSlogan}\n`);
  const structure = p.structure as Record<string, unknown> | undefined;
  if (structure) {
    lines.push('【正文结构】');
    const hook = structure.hook as string | undefined;
    if (hook) lines.push(`Hook: ${hook}`);
    const points = structure.points as string[] | undefined;
    points?.forEach((pt: string) => lines.push(`- ${pt}`));
    const cta = structure.cta as string | undefined;
    if (cta) lines.push(`互动引导: ${cta}`);
    lines.push('');
  }
  const scenes = p.scenes as Array<Record<string, unknown>> | undefined;
  if (scenes) {
    lines.push('【分镜头脚本】');
    scenes.forEach((s) => lines.push(`镜头${s.seq}(${s.seconds}s): ${s.visual}\n旁白: ${s.narration}`));
    lines.push('');
  }
  const outline = p.outline as Array<Record<string, unknown>> | undefined;
  if (outline) {
    lines.push('【文章大纲】');
    outline.forEach((s) => {
      lines.push(`${s.section}. ${s.heading}`);
      const sPoints = s.points as string[] | undefined;
      sPoints?.forEach((pt: string) => lines.push(`  • ${pt}`));
    });
    lines.push('');
  }
  const tags = p.tags as string[] | undefined;
  if (tags) lines.push(`标签：${tags.map((t: string) => `#${t}`).join(' ')}`);
  const tone = p.tone as string | undefined;
  if (tone) lines.push(`风格：${tone}`);
  return lines.join('\n');
}
