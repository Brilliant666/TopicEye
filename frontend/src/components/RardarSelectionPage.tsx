'use client';

import Link from 'next/link';
import type { KeyboardEvent, MouseEvent } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, BookOpenCheck, Boxes, Clock3, Eye, Filter, Radar, ShieldCheck, Star } from 'lucide-react';

import type {
  SelectionCard,
  SelectionCategory,
  SelectionLoadResult,
  SelectionReason,
} from '@/lib/rardar-selection';
import styles from './RardarFoundation.module.css';

type CategoryFilter = 'all' | SelectionCategory;
type ReasonFilter = 'all' | SelectionReason;

const CATEGORIES: Array<{ key: CategoryFilter; label: string }> = [
  { key: 'all', label: '全部方向' },
  { key: 'ai-agent', label: 'AI 与 Agent' },
  { key: 'dev-tools', label: '开发工具' },
  { key: 'data-infra', label: '数据与基础设施' },
  { key: 'productivity', label: '生产力' },
  { key: 'video-content', label: '视频与内容' },
  { key: 'other', label: '其他' },
];
const REASONS: Array<{ key: ReasonFilter; label: string }> = [
  { key: 'all', label: '全部价值' },
  { key: 'directly_reusable', label: '可直接复用' },
  { key: 'specific_problem_solution', label: '解决具体问题' },
  { key: 'distinctive_implementation', label: '实现有辨识度' },
  { key: 'reference_or_learning_value', label: '参考与学习' },
];
const CATEGORY_KEYS = new Set(CATEGORIES.map((item) => item.key));
const REASON_KEYS = new Set(REASONS.map((item) => item.key));

function readFilters(): [CategoryFilter, ReasonFilter] {
  if (typeof window === 'undefined') return ['all', 'all'];
  const query = new URLSearchParams(window.location.search);
  const category = query.get('category') || 'all';
  const reason = query.get('reason') || 'all';
  return [
    CATEGORY_KEYS.has(category as CategoryFilter) ? category as CategoryFilter : 'all',
    REASON_KEYS.has(reason as ReasonFilter) ? reason as ReasonFilter : 'all',
  ];
}

export default function RardarSelectionPage({ result }: { result: SelectionLoadResult }) {
  const [[category, reason], setFilters] = useState<[CategoryFilter, ReasonFilter]>(['all', 'all']);
  useEffect(() => {
    const sync = () => setFilters(readFilters());
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const select = useCallback((nextCategory: CategoryFilter, nextReason: ReasonFilter) => {
    const query = new URLSearchParams(window.location.search);
    if (nextCategory === 'all') query.delete('category'); else query.set('category', nextCategory);
    if (nextReason === 'all') query.delete('reason'); else query.set('reason', nextReason);
    const suffix = query.toString();
    window.history.pushState(null, '', suffix ? `/discover?${suffix}` : '/discover');
    setFilters([nextCategory, nextReason]);
  }, []);

  if (result.kind !== 'published') {
    return (
      <div className={`${styles.page} ${styles.selectionPage}`} data-rardar-route="/discover">
        <SelectionHero count={0} latestCaptureAt={null} />
        <section className={styles.selectionState} data-testid="selection-unavailable">
          <Radar size={28} />
          <h2>{result.kind === 'not_configured' ? '本地「值得看」精选尚未构建' : '精选数据未通过完整性验证'}</h2>
          <p>{result.kind === 'not_configured'
            ? '运行 rardar-local.ps1 build-selection 后，这里会读取不可变的静态 Serving。'
            : '系统已停止读取损坏或不一致的 Selection，不会回退到旧 momentum 列表。'}</p>
          <code>{result.code}</code>
        </section>
      </div>
    );
  }

  const { selection } = result;
  const filtered = selection.items.filter((item) => (
    (category === 'all' || item.category === category)
    && (reason === 'all' || item.primaryReason === reason)
  ));
  const categoryCounts = new Map<CategoryFilter, number>([['all', selection.items.length]]);
  const reasonCounts = new Map<ReasonFilter, number>([['all', selection.items.length]]);
  CATEGORIES.slice(1).forEach(({ key }) => categoryCounts.set(key, selection.items.filter((item) => item.category === key).length));
  REASONS.slice(1).forEach(({ key }) => reasonCounts.set(key, selection.items.filter((item) => item.primaryReason === key).length));

  return (
    <div className={`${styles.page} ${styles.selectionPage}`} data-rardar-route="/discover">
      <SelectionHero count={selection.items.length} latestCaptureAt={selection.latestCaptureAt} />
      {selection.status === 'stale' && (
        <section className={styles.selectionState} data-testid="selection-stale">
          <Clock3 size={22} />
          <h2>本地 Shadow 数据已延迟</h2>
          <p>仍展示最近一次完整验证的 Selection；不会用旧 momentum 列表或实时请求补齐。</p>
        </section>
      )}
      <section className={styles.selectionFilters} aria-label="值得看项目筛选">
        <div><Filter size={15} /><strong>方向</strong></div>
        <nav aria-label="项目方向">
          {CATEGORIES.map((item) => (
            <button key={item.key} type="button" aria-pressed={category === item.key} onClick={() => select(item.key, reason)}>
              {item.label}<span>{categoryCounts.get(item.key) || 0}</span>
            </button>
          ))}
        </nav>
        <div><BookOpenCheck size={15} /><strong>值得看的理由</strong></div>
        <nav aria-label="主价值理由">
          {REASONS.map((item) => (
            <button key={item.key} type="button" aria-pressed={reason === item.key} onClick={() => select(category, item.key)}>
              {item.label}<span>{reasonCounts.get(item.key) || 0}</span>
            </button>
          ))}
        </nav>
      </section>

      <div className={styles.selectionHeading}>
        <div><p>Curated stream</p><h2>本轮值得看的项目</h2></div>
        <span>{filtered.length} 个结果 · 不公开排名</span>
      </div>
      {filtered.length === 0 ? (
        <section className={styles.selectionState}><Eye size={24} /><h2>当前筛选没有项目</h2><p>这是有效的空结果，不会用热度候选补齐。</p></section>
      ) : (
        <section className={styles.selectionGrid} aria-label="Rardar 值得看精选">
          {filtered.map((project) => (
            <SelectionCardView key={project.githubRepositoryId} project={project} generation={selection.generation || ''} />
          ))}
        </section>
      )}
      <section className={styles.selectionCoverage} aria-label="精选覆盖说明">
        <ShieldCheck size={17} />
        <p>{selection.coverageLabelZh}</p>
        <span>Selection {selection.generation?.slice(0, 24)}</span>
      </section>
    </div>
  );
}

function SelectionHero({ count, latestCaptureAt }: { count: number; latestCaptureAt: string | null }) {
  return (
    <section className={styles.selectionHero} data-testid="selection-hero">
      <div>
        <p className={styles.eyebrow}>Discover · Worth seeing</p>
        <h1>Today 之外，找到<span>此刻真正值得理解的项目</span></h1>
        <p>从 Rardar 已验证候选中，分别判断长期价值与为什么是现在；增长只作为时机辅助事实，AI 不修改 Rardar 事实。</p>
        <div className={styles.selectionHeroPills}>
          <span><Boxes size={14} /> {count} 个本地精选</span>
          <span><ShieldCheck size={14} /> 证据绑定 · 无公开排名</span>
          <span><Radar size={14} /> 本地 Shadow · 不影响 Production</span>
        </div>
      </div>
      <dl>
        <div><dt>数据基线</dt><dd>{latestCaptureAt ? formatTime(latestCaptureAt) : '等待构建'}</dd></div>
        <div><dt>事实来源</dt><dd>Observation + Canonical Profile</dd></div>
        <div><dt>页面调用</dt><dd>0 GitHub · 0 模型</dd></div>
      </dl>
    </section>
  );
}

function SelectionCardView({ project, generation }: { project: SelectionCard; generation: string }) {
  const detailHref = `/project/github/${project.githubRepositoryId}?selectionGeneration=${encodeURIComponent(generation)}`;
  const navigate = () => window.location.assign(detailHref);
  const onClick = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('a, button, input, select, textarea')) return;
    navigate();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget || !['Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    navigate();
  };
  return (
    <article
      className={styles.selectionCard}
      data-testid="selection-project-card"
      role="link"
      tabIndex={0}
      aria-label={`查看 ${project.repository} 的值得看详情`}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <div className={styles.selectionCardTopline}>
        <span>{categoryLabel(project.category)}</span>
        <span>{reasonLabel(project.primaryReason)}</span>
      </div>
      <h3><Link href={detailHref}>{project.repository}<ArrowRight size={15} /></Link></h3>
      <p className={styles.selectionIdentity}>{project.identitySummaryZh}</p>
      {project.corePositioningZh && <p className={styles.selectionPositioning}>{project.corePositioningZh}</p>}
      <section className={styles.selectionWhy}><strong>为什么值得看</strong><p>{project.whyWorthSeeingZh}</p></section>
      {project.whyNowZh && <section className={styles.selectionWhyNow}><Clock3 size={15} /><p>{project.whyNowZh}</p></section>}
      <div className={styles.selectionTags}>
        {project.supportingReasons.map((item) => <span key={item}>{reasonLabel(item)}</span>)}
        {project.productFormsZh.slice(0, 2).map((item) => <span key={item}>{item}</span>)}
        {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
        {project.topics.slice(0, 2).map((item) => <span key={item}>{item}</span>)}
        {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
      </div>
      <footer>
        <span>{project.momentumLabel || <><Star size={13} /> {formatNumber(project.totalStars)} total</>}</span>
        <div>
          <Link href={`/find?repositoryUrl=${encodeURIComponent(project.htmlUrl)}`}>评估复用 <ArrowRight size={13} /></Link>
          <a href={project.htmlUrl} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13} /></a>
        </div>
      </footer>
    </article>
  );
}

export function filterSelection(
  projects: SelectionCard[],
  category: CategoryFilter,
  reason: ReasonFilter,
) {
  return projects.filter((item) => (
    (category === 'all' || item.category === category)
    && (reason === 'all' || item.primaryReason === reason)
  ));
}

function categoryLabel(value: SelectionCategory) {
  return CATEGORIES.find((item) => item.key === value)?.label || '其他';
}

function reasonLabel(value: SelectionReason) {
  return REASONS.find((item) => item.key === value)?.label || value;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}
