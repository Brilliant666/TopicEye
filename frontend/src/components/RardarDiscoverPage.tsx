'use client';

import Link from 'next/link';
import type { KeyboardEvent, MouseEvent } from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Clock3,
  Eye,
  GitBranch,
  Radar,
  ShieldCheck,
  Star,
} from 'lucide-react';

import {
  type DiscoverCard,
  type DiscoverCategory,
  type DiscoverLoadResult,
  type DiscoverResponse,
  type DiscoverStage,
} from '@/lib/rardar-discover';
import styles from './RardarFoundation.module.css';

type CategoryFilter = 'all' | DiscoverCategory;

const CATEGORIES: Array<{ key: CategoryFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'ai-agent', label: 'AI 与 Agent' },
  { key: 'dev-tools', label: '开发工具' },
  { key: 'data-infra', label: '数据与基础设施' },
  { key: 'productivity', label: '生产力' },
  { key: 'video-content', label: '视频与内容' },
  { key: 'other', label: '其他' },
];
const CATEGORY_KEYS = new Set(CATEGORIES.map((item) => item.key));

const SECTIONS: Array<{
  key: keyof DiscoverResponse['stages'];
  stage: DiscoverStage;
  title: string;
  description: string;
}> = [
  {
    key: 'justDiscovered',
    stage: 'just_discovered',
    title: '刚刚发现',
    description: '最近 4 小时首次进入候选池；这是新召回事实，尚未形成增长结论。',
  },
  {
    key: 'outsideTodayMomentum',
    stage: 'outside_today_momentum',
    title: '榜外异动',
    description: '已形成完整 24 小时事实但未进入 Today Top 20；最近短窗口出现连续增长和加速。',
  },
  {
    key: 'rising',
    stage: 'rising',
    title: '持续升温',
    description: '已通过实际增长门禁，并有连续正增长 Observation 作为证据。',
  },
  {
    key: 'nearValidation',
    stage: 'near_validation',
    title: '待日榜验证',
    description: '已通过同一信号门禁并连续观察至少 20 小时，等待下一次 08:00 日榜结算。',
  },
];

export function filterDiscoverStages(
  stages: DiscoverResponse['stages'],
  category: CategoryFilter,
): DiscoverResponse['stages'] {
  if (category === 'all') return stages;
  return {
    justDiscovered: stages.justDiscovered.filter((item) => item.category === category),
    outsideTodayMomentum: stages.outsideTodayMomentum.filter((item) => item.category === category),
    rising: stages.rising.filter((item) => item.category === category),
    nearValidation: stages.nearValidation.filter((item) => item.category === category),
  };
}

function categoryFromLocation(): CategoryFilter {
  if (typeof window === 'undefined') return 'all';
  const candidate = new URL(window.location.href).searchParams.get('category') || 'all';
  return CATEGORY_KEYS.has(candidate as CategoryFilter) ? candidate as CategoryFilter : 'all';
}

export default function RardarDiscoverPage({ result }: { result: DiscoverLoadResult }) {
  const [category, setCategory] = useState<CategoryFilter>('all');

  useEffect(() => {
    const sync = () => setCategory(categoryFromLocation());
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

  const selectCategory = useCallback((next: CategoryFilter) => {
    setCategory(next);
    const url = new URL(window.location.href);
    if (next === 'all') url.searchParams.delete('category');
    else url.searchParams.set('category', next);
    window.history.pushState({ category: next }, '', `${url.pathname}${url.search}${url.hash}`);
  }, []);

  if (result.kind !== 'published') {
    return (
      <div className={`${styles.page} ${styles.discoverRealtimePage}`} data-rardar-route="/discover">
        <DiscoverHero board={null} category="all" publishedCount={0} />
        <section className={styles.discoverUnavailable} role="status">
          <Radar size={24} />
          <div>
            <h2>{result.kind === 'not_configured' ? '近实时发现尚未同步' : '近实时发现完整性验证失败'}</h2>
            <p>系统没有回退到 Demo 或旧的未验证数据。事实链恢复后，这里会自动显示新的完整 Serving。</p>
            <code>{result.code}</code>
          </div>
        </section>
      </div>
    );
  }
  const { board } = result;
  const filtered = filterDiscoverStages(board.stages, category);
  const allCards = [
    ...board.stages.justDiscovered,
    ...board.stages.outsideTodayMomentum,
    ...board.stages.rising,
    ...board.stages.nearValidation,
  ];
  const publishedCount = filtered.justDiscovered.length
    + filtered.outsideTodayMomentum.length
    + filtered.rising.length
    + filtered.nearValidation.length;
  const categoryCounts = new Map<CategoryFilter, number>([['all', allCards.length]]);
  CATEGORIES.slice(1).forEach(({ key }) => {
    categoryCounts.set(key, allCards.filter((item) => item.category === key).length);
  });

  return (
    <div className={`${styles.page} ${styles.discoverRealtimePage}`} data-rardar-route="/discover">
      <DiscoverHero board={board} category={category} publishedCount={publishedCount} />
      <nav className={styles.discoverCategoryFilters} aria-label="发现项目分类">
        {CATEGORIES.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-pressed={category === item.key}
            data-selected={category === item.key ? 'true' : 'false'}
            onClick={() => selectCategory(item.key)}
          >
            {item.label}<span>{categoryCounts.get(item.key) || 0}</span>
          </button>
        ))}
      </nav>
      <div className={styles.discoverStageFlow}>
        {SECTIONS.map((section) => (
          <DiscoverSection
            key={section.key}
            title={section.title}
            description={section.stage === 'outside_today_momentum'
              ? `已形成完整 24 小时事实但未进入 Today Top ${board.todayPublishedTopCount ?? 20}；最近短窗口出现连续增长和加速。`
              : section.description}
            stage={section.stage}
            projects={filtered[section.key]}
            generation={board.generation || ''}
            category={category}
          />
        ))}
      </div>
      <Coverage board={board} />
    </div>
  );
}

function DiscoverHero({
  board,
  category,
  publishedCount,
}: {
  board: DiscoverResponse | null;
  category: CategoryFilter;
  publishedCount: number;
}) {
  const suppressed = board?.eligibilitySummary?.suppressed
    ?? (board?.suppressionSummary && 'suppressedWeakSignalCount' in board.suppressionSummary
      ? board.suppressionSummary.suppressedWeakSignalCount
      : undefined);
  return (
    <section className={styles.discoverRealtimeHero} data-testid="discover-hero">
      <div>
        <p className={styles.eyebrow}>Discover · Near real-time</p>
        <h1>发现此刻正在形成的真实信号</h1>
        <p>
          来自 Rardar 每 2 小时一次的已验证 Observation。新候选展示真实观察窗口；榜外项目同时说明
          Today exact 事实和最近短窗口异动，全部不做 24 小时外推。
        </p>
        <div className={styles.discoverHeroMetrics} aria-label="当前发现状态">
          <span>当前筛选 <strong>{categoryLabel(category)}</strong></span>
          <span>发布 <strong>{publishedCount}</strong></span>
          <span>弱信号抑制 <strong>{suppressed ?? '—'}</strong></span>
        </div>
      </div>
      <div className={styles.discoverFreshness}>
        <span className={board?.freshnessState === 'stale' ? styles.staleBadge : styles.freshBadge}>
          <ShieldCheck size={14} />
          {board?.freshnessState === 'stale' ? '数据已延迟' : '数据已验证'}
        </span>
        <dl>
          <div><dt>最近更新</dt><dd>{board?.latestCaptureAt ? formatTime(board.latestCaptureAt) : '等待同步'}</dd></div>
          <div><dt>最新 Capture</dt><dd>{board?.latestCaptureId || '—'}</dd></div>
          <div><dt>下次预计</dt><dd>{board?.nextExpectedAt ? formatTime(board.nextExpectedAt) : '—'}</dd></div>
          <div><dt>更新节奏</dt><dd>每 2 小时</dd></div>
        </dl>
      </div>
    </section>
  );
}

function DiscoverSection({
  title,
  description,
  stage,
  projects,
  generation,
  category,
}: {
  title: string;
  description: string;
  stage: DiscoverStage;
  projects: DiscoverCard[];
  generation: string;
  category: CategoryFilter;
}) {
  return (
    <section className={styles.discoverStageSection} data-testid={`discover-stage-${stage}`}>
      <header>
        <div><span className={styles.discoverStageMarker} data-stage={stage} /><div><h2>{title}</h2><p>{description}</p></div></div>
        <span>{projects.length} 个项目</span>
      </header>
      {projects.length === 0 ? (
        <div className={styles.discoverStageEmpty}>
          <Eye size={20} />
          <p>{category === 'all'
            ? '本次已验证 Observation 中没有符合该阶段信号门禁的项目。'
            : `${categoryLabel(category)}中暂时没有符合该阶段信号门禁的项目。`}</p>
        </div>
      ) : (
        <div className={styles.discoverRealtimeGrid}>
          {projects.map((project) => (
            <DiscoverCardView key={project.githubRepositoryId} project={project} generation={generation} />
          ))}
        </div>
      )}
    </section>
  );
}

function DiscoverCardView({ project, generation }: { project: DiscoverCard; generation: string }) {
  const detailHref = `/project/github/${project.githubRepositoryId}?discoverGeneration=${encodeURIComponent(generation)}`;
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
      className={styles.discoverRealtimeCard}
      data-testid="discover-project-card"
      role="link"
      tabIndex={0}
      aria-label={`查看 ${project.repository} 的发现详情`}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <div className={styles.discoverCardTopline}>
        <div>
          <span data-kind="category">{categoryLabel(project.category || 'other')}</span>
          <span data-kind="stage">{stageLabel(project.stage)}</span>
        </div>
        <small>{sourceLabel(project.sourceMode)}</small>
      </div>
      <h3><Link href={detailHref}>{project.repository} <ArrowRight size={15} /></Link></h3>
      <p className={styles.discoverIdentity}>{project.identitySummaryZh}</p>
      <p className={styles.discoverPositioning}>{project.positioningZh}</p>
      <div className={styles.discoverCapabilityTags}>
        {project.capabilities.slice(0, 3).map((item) => <span key={`${item.title}-${item.detail}`}>{item.title}</span>)}
      </div>
      <dl className={styles.discoverCardFacts}>
        {project.stage === 'outside_today_momentum' ? (
          <>
            <div className={styles.discoverGrowthFact}>
              <dt>最近实际 {formatHours(project.recentWindowHours ?? 0)}</dt>
              <dd>+{formatNumber(project.recentObservedStarDelta ?? 0)} <small>/ 短窗口异动</small></dd>
            </div>
            <div><dt>前一相同窗口</dt><dd>{signedNumber(project.priorComparableWindowDelta)}</dd></div>
            <div><dt>加速变化</dt><dd>{signedNumber(project.accelerationDelta)}</dd></div>
            <div><dt>Today exact</dt><dd>#{project.todayExactRank ?? '—'} · 24h +{formatNumber(project.todayExact24hDelta ?? 0)}</dd></div>
          </>
        ) : (
        <div className={styles.discoverGrowthFact}>
          <dt>实际增长</dt>
          <dd>+{formatNumber(project.observedStarDelta)} <small>/ 实际 {formatHours(project.observedWindowHours)}</small></dd>
        </div>
        )}
        <div><dt>当前 Star</dt><dd><Star size={13} /> {formatNumber(project.totalStars)}</dd></div>
        <div><dt>正增长连续性</dt><dd>{project.consecutivePositiveIntervalCount == null ? '尚未形成结论' : `${project.consecutivePositiveIntervalCount} 个连续区间`}</dd></div>
        {project.stage !== 'outside_today_momentum' && <div><dt>首次发现</dt><dd>{formatTime(project.firstSeenAt)}</dd></div>}
        {project.stage !== 'outside_today_momentum' && <div><dt>最新区间</dt><dd>{project.latestIntervalDelta == null ? '尚无连续区间' : `${project.latestIntervalDelta >= 0 ? '+' : ''}${project.latestIntervalDelta} Star`}</dd></div>}
      </dl>
      <div className={styles.discoverMetadata}>
        {project.language && <span>{project.language}</span>}
        {project.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
        {project.license && <span>{project.license}</span>}
        {project.isFork && <span><GitBranch size={11} /> Fork</span>}
        {project.isArchived && <span>Archived</span>}
      </div>
      <div className={styles.discoverCardFooter}>
        <span>点击卡片查看发现证据</span>
        <a href={project.url} target="_blank" rel="noreferrer" aria-label={`在 GitHub 打开 ${project.repository}`}>
          GitHub <ArrowUpRight size={14} />
        </a>
      </div>
    </article>
  );
}

function Coverage({ board }: { board: DiscoverResponse }) {
  const coverage = board.coverage;
  if (!coverage) return null;
  return (
    <details className={styles.discoverCoverage}>
      <summary><Clock3 size={15} /> 查看本轮召回与完整性范围</summary>
      <div>
        <span>候选 {coverage.candidateCount}</span>
        <span>发布 {coverage.publishedCount}</span>
        {board.eligibilitySummary && <span>Today exact {board.eligibilitySummary.todayExactFacts}</span>}
        {board.eligibilitySummary && <span>Today 已发布 {board.eligibilitySummary.todayPublished}</span>}
        {board.eligibilitySummary && <span>榜外已评估 {board.eligibilitySummary.exactOutsidePublishedEvaluated}</span>}
        {board.eligibilitySummary && <span>Pre-exact 已评估 {board.eligibilitySummary.preExactEvaluated}</span>}
        {board.eligibilitySummary && <span>信号抑制 {board.eligibilitySummary.suppressed}</span>}
        <span>成功查询 {coverage.querySuccessCount}</span>
        <span>失败查询 {coverage.queryFailureCount}</span>
        <span>Metadata failure {coverage.metadataFailureCount}</span>
        {coverage.excludedExactCount != null && <span>旧合同排除 Today exact {coverage.excludedExactCount}</span>}
        {coverage.excludedPublishedCount != null && <span>排除 Today Top 20 {coverage.excludedPublishedCount}</span>}
        <span>冲突 {coverage.conflictCount}</span>
        <span>来源 capture {coverage.sourceCaptureCount}</span>
      </div>
      <p>这是多源候选召回与连续观察的覆盖，不代表 GitHub 全站绝对完整扫描。</p>
    </details>
  );
}

function stageLabel(value: DiscoverStage) {
  return {
    just_discovered: '刚刚发现',
    outside_today_momentum: '榜外异动',
    rising: '持续升温',
    near_validation: '待日榜验证',
  }[value];
}

function categoryLabel(value: CategoryFilter) {
  return CATEGORIES.find((item) => item.key === value)?.label || '其他';
}

function sourceLabel(value: DiscoverCard['sourceMode']) {
  return { official_zh: '官方中文', official_translated: '官方资料译', rardar_derived: 'Rardar 整理' }[value];
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function signedNumber(value: number | null | undefined) {
  if (value == null) return '窗口证据不足';
  return `${value >= 0 ? '+' : ''}${formatNumber(value)} Star`;
}

function formatHours(value: number) {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} 小时`;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}
