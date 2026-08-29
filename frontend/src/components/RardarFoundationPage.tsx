import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Clock3,
  Construction,
  DatabaseZap,
  FolderGit2,
  Radar,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Star,
} from 'lucide-react';

import { isRardarProduct } from '@/lib/product-profile';
import { RARDAR_FOUNDATION_PAGES, type RardarFoundationPageKey } from '@/lib/rardar-foundation';
import {
  loadExplosionBoard,
  loadTodaySnapshot,
  type ExplosionBoard,
  type ExplosionBoardLoadResult,
  type ExplosionWindow,
  type PendingExplosionProject,
  type TodayLoadResult,
  type TodayProject,
  type TodaySnapshot,
} from '@/lib/rardar-intelligence';
import styles from './RardarFoundation.module.css';
import RardarProjectExplanation from './RardarProjectExplanation';

export default async function RardarFoundationPage({ pageKey }: { pageKey: RardarFoundationPageKey }) {
  if (!isRardarProduct()) notFound();

  if (pageKey === 'today') return <TodayFoundation result={await loadTodaySnapshot()} />;
  if (pageKey === 'discover') return <DiscoverFoundation result={await loadExplosionBoard()} />;

  const page = RARDAR_FOUNDATION_PAGES[pageKey];
  return (
    <div className={styles.page} data-rardar-route={page.href}>
      <section className={styles.emptyCard}>
        <div className={styles.emptyContent}>
          <span className={styles.emptyIcon} aria-hidden="true"><Construction size={30} /></span>
          <p className={styles.eyebrow}>{page.eyebrow}</p>
          <h1>{page.title}</h1>
          <p>{page.description}</p>
          <div className={styles.slotLabel}>{page.slot}</div>
          <p className={styles.nextStep}>{page.nextStep}</p>
        </div>
      </section>
    </div>
  );
}

export function TodayFoundation({ result }: { result: TodayLoadResult }) {
  const board = result.kind === 'published' ? result.board : null;

  return (
    <div className={`${styles.page} ${styles.todayPage}`} data-rardar-route="/">
      <section className={`${styles.hero} ${styles.todayHero}`} data-testid="today-hero">
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>Today · Exact 24h</p>
          <h1 className={styles.heroTitle}>
            过去完整 24 小时，哪些项目获得了
            <span className={styles.heroTitleAccent}>最多新增关注？</span>
          </h1>
          <p className={styles.heroDescription}>
            Rardar 连续观察多源候选，按 observedStarDelta 排出完整 24h 榜；
            AI 只做解读，不参与排名、过滤或补齐。
          </p>
          <div className={styles.foundationNotice}>
            <span className={styles.noticePill}>
              <ShieldCheck size={15} aria-hidden="true" />
              {board?.dataLabel || '真实数据模式'}
            </span>
            <span className={styles.noticePill}>
              <Sparkles size={15} aria-hidden="true" /> AI 解读按需生成，不改变事实名次
            </span>
          </div>
        </div>
      </section>

      <div className={styles.sectionHeading}>
        <div><h2>精确 24 小时榜</h2><p>默认 Top 10，可展开至 Artifact 中的 Top 20。</p></div>
        {board?.window?.endedAt && <span className={styles.timestamp}>窗口截止 {formatTime(board.window.endedAt)}</span>}
      </div>

      <TodayState result={result} />
    </div>
  );
}

function TodayState({ result }: { result: TodayLoadResult }) {
  if (result.kind === 'not_configured') return <NotSyncedCard />;
  if (result.kind === 'error') {
    return <StatusCard icon={AlertTriangle} title="真实情报数据暂时不可用" detail={`已安全停止读取 · ${result.code}`} tone="danger" />;
  }
  const board = result.board;
  if (board.state === 'not_ready') {
    return <StatusCard icon={Clock3} title="今日爆发事实尚未发布" detail="当前 generation 健康，但尚未包含 Explosion Artifact。" />;
  }

  const generationId = board.generationId;
  if (!generationId || board.state !== 'ready' || board.exactRanked.length === 0) {
    return (
      <>
        <section className={styles.emptyExactCard}>
          <Clock3 size={28} aria-hidden="true" />
          <div>
            <h3>尚未形成完整 24 小时精确榜</h3>
            <p>当前状态为 {windowStateLabel(board.window?.state)}。Rardar 不会用短窗口增量或演示项目补齐名次。</p>
          </div>
        </section>
        <DiscoverLink count={board.coverage?.pendingCount ?? board.pendingRanked.length} />
        <Provenance board={board} />
      </>
    );
  }

  const exact = board.exactRanked.slice(0, 20);
  return (
    <>
      <section className={styles.rankingList} aria-label="GitHub 精确 24 小时爆发榜 Top 10">
        {exact.slice(0, 10).map((project) => (
          <ExactProjectCard key={project.githubRepositoryId} project={project} generationId={generationId} />
        ))}
      </section>
      {exact.length > 10 && (
        <details className={styles.expandBoard}>
          <summary><span className={styles.expandClosed}>查看 Top {exact.length}</span><span className={styles.expandOpen}>收起</span></summary>
          <section className={styles.rankingList} aria-label={`GitHub 精确 24 小时爆发榜第 11 至 ${exact.length} 名`}>
            {exact.slice(10).map((project) => (
              <ExactProjectCard key={project.githubRepositoryId} project={project} generationId={generationId} />
            ))}
          </section>
        </details>
      )}
      <DiscoverLink count={board.coverage?.pendingCount ?? board.pendingRanked.length} />
      <Provenance board={board} />
    </>
  );
}

export function DiscoverFoundation({ result }: { result: ExplosionBoardLoadResult }) {
  const board = result.kind === 'published' ? result.board : null;
  return (
    <div className={styles.page} data-rardar-route="/discover">
      <section className={`${styles.hero} ${styles.discoverHero}`}>
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>Discover · Early Signals</p>
          <h1 className={styles.heroTitle}>刚被雷达捕获，<span className={styles.heroTitleAccent}>正在积累观察</span></h1>
          <p className={styles.heroDescription}>
            这里只展示 Artifact 的 pending 事实。窗口内增量保持原值，不线性外推 24 小时，也不把候选池或 AI 判断混进来。
          </p>
          <div className={styles.foundationNotice}>
            <span className={styles.noticePill}><SearchCheck size={15} /> 最多展示当前 Top 20 待验证项目</span>
            {board && <span className={styles.noticePill}><Clock3 size={15} /> {windowStateLabel(board.window?.state)}</span>}
          </div>
        </div>
      </section>

      <DiscoverState result={result} />
    </div>
  );
}

function DiscoverState({ result }: { result: ExplosionBoardLoadResult }) {
  if (result.kind === 'not_configured') return <NotSyncedCard />;
  if (result.kind === 'error') {
    return <StatusCard icon={AlertTriangle} title="真实发现数据暂时不可用" detail={`已安全停止读取 · ${result.code}`} tone="danger" />;
  }
  const board = result.board;
  if (board.state === 'not_synced') return <NotSyncedCard />;
  if (board.state === 'not_ready') {
    return <StatusCard icon={Clock3} title="发现数据尚未发布" detail="当前 generation 尚未包含可验证的 Explosion Artifact。" />;
  }
  const generationId = board.generationId;
  const pending = board.pendingRanked.slice(0, 20);
  if (!generationId || pending.length === 0) {
    return (
      <>
        <StatusCard icon={Radar} title="当前没有待验证项目" detail="发现页不会用 exact 项目或原始候选池填充空位。" />
        <Provenance board={board} />
      </>
    );
  }

  const counts = pending.reduce(
    (summary, item) => {
      summary[pendingStage(item)] += 1;
      return summary;
    },
    { new: 0, observing: 0, near: 0 },
  );
  return (
    <>
      <div className={styles.sectionHeading}>
        <div><h2>待验证项目</h2><p>展示 {pending.length} / {board.coverage?.pendingCount ?? board.pendingRanked.length} · 保持 Artifact pendingRank。</p></div>
        <span className={styles.timestamp}>刚被发现 {counts.new} · 观察中 {counts.observing} · 接近验证 {counts.near}</span>
      </div>
      <section className={styles.discoverGrid} aria-label="正在积累观察的项目">
        {pending.map((project) => (
          <PendingProjectCard key={project.githubRepositoryId} project={project} generationId={generationId} />
        ))}
      </section>
      <Provenance board={board} />
    </>
  );
}

function ExactProjectCard({ project, generationId }: { project: TodayProject; generationId: string }) {
  const relativeGrowth = project.baselineStars > 0 ? project.observedStarDelta / project.baselineStars : null;
  const detailHref = `/project/github/${project.githubRepositoryId}?generation=${encodeURIComponent(generationId)}`;
  return (
    <article className={styles.rankingCard} data-testid={`today-project-${project.rank}`}>
      <div className={styles.rank}>#{project.rank}</div>
      <div className={styles.projectIdentity}>
        <Link href={detailHref} className={styles.repository}>
          <FolderGit2 size={18} aria-hidden="true" /> {project.repository} <ArrowRight size={15} aria-hidden="true" />
        </Link>
        <p className={styles.projectDescription}>{project.officialSummaryZh}</p>
        {project.capabilities.length > 0 && (
          <ul className={styles.capabilityList} aria-label="核心能力摘要" data-testid="today-capabilities">
            {project.capabilities.slice(0, project.rank <= 3 ? 3 : 2).map((capability) => (
              <li key={`${capability.title}-${capability.detail}`}>
                <strong>{capability.title}</strong>
                <span>{capability.shortDetail || capability.detail}</span>
              </li>
            ))}
          </ul>
        )}
        <div className={styles.tags}>
          {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
          {project.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
          {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
          <span>{project.sourceLabel}</span>
          <span>事实 · 精确 24h</span>
          {relativeGrowth !== null && <span>相对增长 {(relativeGrowth * 100).toFixed(1)}%</span>}
        </div>
        <div className={styles.cardActions}>
          <Link className={styles.findPrefillLink} href={detailHref}>查看项目详情 <ArrowRight size={14} /></Link>
          <a className={styles.githubLink} href={project.htmlUrl} target="_blank" rel="noreferrer">
            GitHub <ArrowUpRight size={14} />
          </a>
        </div>
      </div>
      <div className={styles.starFacts}>
        <strong>+{formatNumber(project.observedStarDelta)}</strong>
        <span><Star size={14} aria-hidden="true" /> {formatNumber(project.totalStars)} total</span>
        <small>截止 {formatTime(project.windowEndedAt)}</small>
      </div>
    </article>
  );
}

function PendingProjectCard({ project, generationId }: { project: PendingExplosionProject; generationId: string }) {
  const stage = pendingStage(project);
  return (
    <article className={styles.pendingCard}>
      <div className={styles.pendingTopline}>
        <span className={styles.pendingBadge}>待验证 #{project.pendingRank}</span>
        <span className={`${styles.stageBadge} ${styles[`stage_${stage}`]}`}>{pendingStageLabel(stage)}</span>
      </div>
      <a href={project.htmlUrl} target="_blank" rel="noreferrer">{project.repository}<ArrowUpRight size={13} /></a>
      <p className={styles.pendingDescription}>{project.description || 'GitHub 暂未提供官方 Description。'}</p>
      <dl className={styles.pendingFacts}>
        <div><dt>当前 Star</dt><dd>{formatNumber(project.totalStars)}</dd></div>
        <div><dt>观测时长</dt><dd>{project.observedWindowHours === null ? '等待第二个观察点' : `${project.observedWindowHours.toFixed(1)}h`}</dd></div>
        <div><dt>窗口内增量</dt><dd>{formatSigned(project.observedWindowStarDelta)}</dd></div>
        <div><dt>待验证原因</dt><dd>{pendingReasonLabel(project.pendingReason)}</dd></div>
        <div><dt>首次发现</dt><dd>{formatTime(project.firstSeenAt)}</dd></div>
        <div><dt>观测窗口</dt><dd>{formatWindow(project.observedWindowStartedAt, project.observedWindowEndedAt)}</dd></div>
      </dl>
      <div className={styles.tags}>
        {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
        {project.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
        {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
      </div>
      <div className={styles.cardActions}>
        <RardarProjectExplanation
          repository={project.repository}
          generationId={generationId}
        />
        <FindPrefillLink htmlUrl={project.htmlUrl} />
      </div>
    </article>
  );
}

function FindPrefillLink({ htmlUrl }: { htmlUrl: string }) {
  return (
    <Link className={styles.findPrefillLink} href={`/find?repositoryUrl=${encodeURIComponent(htmlUrl)}`}>
      用这个仓库评估我的需求 <ArrowRight size={14} />
    </Link>
  );
}

function DiscoverLink({ count }: { count: number }) {
  return (
    <Link href="/discover" className={styles.discoverLink}>
      <Radar size={17} /> 发现 {count} 个正在积累观察的项目 <ArrowRight size={15} />
    </Link>
  );
}

function NotSyncedCard() {
  return (
    <StatusCard
      icon={DatabaseZap}
      title="真实数据尚未同步"
      detail="运行 powershell -ExecutionPolicy Bypass -File .\\scripts\\rardar-local.ps1 sync-data。系统不会静默切换到演示榜。"
    />
  );
}

function Provenance({ board }: { board: ExplosionBoard | TodaySnapshot }) {
  return (
    <section className={styles.provenanceBar} aria-label="真实数据来源和 generation">
      <div><ShieldCheck size={18} /><span>{board.dataLabel}</span></div>
      <span>状态 {windowStateLabel(board.window?.state)}</span>
      {board.window && <span>截止 {formatTime(board.window.endedAt)}</span>}
      {board.syncedAt && <span>本地同步 {formatTime(board.syncedAt)}</span>}
      <span>精确 {board.coverage?.exactCount ?? board.exactRanked.length} · 待验证 {board.coverage?.pendingCount ?? board.pendingRanked.length}</span>
      {board.coverage && (
        <span>
          查询成功 {board.coverage.successfulQueryCount} · 失败 {board.coverage.failedQueryCount}
          {board.coverage.metadataFailureCount > 0 ? ` · 元数据缺失 ${board.coverage.metadataFailureCount}` : ''}
        </span>
      )}
      {board.sourceHost && <span>来源 {board.sourceHost}</span>}
      {board.artifactSha256 && <span title={board.artifactSha256}>Artifact {board.artifactSha256.slice(0, 10)}</span>}
      {board.generationId && <code>{board.generationId}</code>}
    </section>
  );
}

function StatusCard({ icon: Icon, title, detail, tone = 'default' }: { icon: typeof Radar; title: string; detail: string; tone?: 'default' | 'danger' }) {
  return (
    <section className={`${styles.emptyCard} ${tone === 'danger' ? styles.errorCard : ''}`}>
      <div className={styles.emptyContent}>
        <span className={styles.emptyIcon} aria-hidden="true"><Icon size={30} /></span>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </section>
  );
}

function pendingStage(project: PendingExplosionProject): 'new' | 'observing' | 'near' {
  if (project.observedWindowHours === null || project.observedWindowHours < 6) return 'new';
  if (project.observedWindowHours < 18) return 'observing';
  return 'near';
}

function pendingStageLabel(value: 'new' | 'observing' | 'near') {
  return { new: '刚被发现', observing: '观察中', near: '接近验证' }[value];
}

function pendingReasonLabel(value: PendingExplosionProject['pendingReason']) {
  return { first_seen: '首次发现', baseline_missing: '缺少完整基线', baseline_ineligible: '基线尚不满足条件' }[value];
}

function windowStateLabel(value: ExplosionWindow['state'] | undefined) {
  return value === 'exact' ? '精确 24h' : value === 'warming_up' ? '基线积累中' : value === 'baseline_missing' ? '基线缺失' : '尚未发布';
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatSigned(value: number | null) {
  if (value === null) return '增量待确认';
  return `${value >= 0 ? '+' : ''}${formatNumber(value)} Star`;
}

function formatWindow(start: string | null, end: string | null) {
  if (!start || !end) return '等待完整观测点';
  return `${formatTime(start)} → ${formatTime(end)}`;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}
