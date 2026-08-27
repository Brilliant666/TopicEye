import { notFound } from 'next/navigation';
import {
  AlertTriangle,
  ArrowUpRight,
  Clock3,
  Construction,
  DatabaseZap,
  FolderGit2,
  Radar,
  ShieldCheck,
  Sparkles,
  Star,
} from 'lucide-react';

import { isRardarProduct } from '@/lib/product-profile';
import {
  RARDAR_FOUNDATION_PAGES,
  type RardarFoundationPageKey,
} from '@/lib/rardar-foundation';
import {
  loadExplosionBoard,
  type ExplosionBoardLoadResult,
  type ExactExplosionProject,
  type PendingExplosionProject,
} from '@/lib/rardar-intelligence';
import styles from './RardarFoundation.module.css';
import RardarProjectExplanation from './RardarProjectExplanation';

export default async function RardarFoundationPage({ pageKey }: { pageKey: RardarFoundationPageKey }) {
  if (!isRardarProduct()) notFound();

  const page = RARDAR_FOUNDATION_PAGES[pageKey];
  if (pageKey === 'today') return <TodayFoundation result={await loadExplosionBoard()} />;

  return (
    <div className={styles.page} data-rardar-route={page.href}>
      <section className={styles.emptyCard}>
        <div className={styles.emptyContent}>
          <span className={styles.emptyIcon} aria-hidden="true">
            <Construction size={30} />
          </span>
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

export function TodayFoundation({ result }: { result: ExplosionBoardLoadResult }) {
  const today = RARDAR_FOUNDATION_PAGES.today;
  const board = result.kind === 'published' ? result.board : null;

  return (
    <div className={styles.page} data-rardar-route="/">
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>
            {board?.dataMode === 'demo' ? 'Today · Local Demo Data' : today.eyebrow}
          </p>
          <h1 className={styles.heroTitle}>
            把 GitHub 热点变成
            <span className={styles.heroTitleAccent}>可行动的开发情报</span>
          </h1>
          <p className={styles.heroDescription}>
            基于 Rardar 多源候选召回与自有连续观察形成的 GitHub 24h 爆发榜。
            名次只来自经过 Hash、Schema 与来源版本验证的客观 Star 增量。
          </p>
          <div className={styles.foundationNotice}>
            <span className={styles.noticePill}>
              <ShieldCheck size={15} aria-hidden="true" />
              {board?.dataMode === 'demo' ? '本地演示数据 · 非实时榜' : '已验证事实链'}
            </span>
            <span className={styles.noticePill}>
              <Sparkles size={15} aria-hidden="true" /> AI 解读按需生成，不参与排名
            </span>
          </div>
        </div>
      </section>

      <div className={styles.sectionHeading}>
        <div>
          <h2>过去 24 小时</h2>
          <p>精确 Top 5 · observedStarDelta 降序 · AI 不参与名次</p>
        </div>
        {board?.capturedAt && <span className={styles.timestamp}>更新于 {formatTime(board.capturedAt)}</span>}
      </div>

      <ExplosionState result={result} />
    </div>
  );
}

function ExplosionState({ result }: { result: ExplosionBoardLoadResult }) {
  if (result.kind === 'not_configured') {
    return <StatusCard icon={DatabaseZap} title="情报数据尚未配置" detail="配置正式 Rardar data 根目录后，页面才会读取已发布 generation；不会回退到 fixture。" />;
  }
  if (result.kind === 'error') {
    return <StatusCard icon={AlertTriangle} title="情报数据暂时不可用" detail={`读取已安全停止 · ${result.code}`} tone="danger" />;
  }
  const board = result.board;
  if (board.state === 'not_ready') {
    return <StatusCard icon={Clock3} title="今日爆发事实尚未发布" detail="当前 generation 健康，但尚未包含 Explosion Artifact。" />;
  }
  if (board.state === 'warming_up') {
    return (
      <>
        <StatusCard icon={Clock3} title="24 小时观察基线正在建立" detail="新项目会进入待验证区；在完整 24h 基线形成前不会冒充精确榜单。" />
        <PendingFacts board={board} />
      </>
    );
  }
  if (board.state === 'baseline_missing') {
    return (
      <>
        <StatusCard icon={AlertTriangle} title="本期 24 小时基线缺失" detail="系统保留可追溯的待验证事实，但不会推测或补造精确名次。" />
        <PendingFacts board={board} />
      </>
    );
  }
  return <ReadyBoard board={board} />;
}

function ReadyBoard({ board }: { board: Extract<ExplosionBoardLoadResult, { kind: 'published' }>['board'] }) {
  const exact = board.exactRanked.slice(0, 5);
  return (
    <>
      <section className={styles.rankingList} aria-label="GitHub 24 小时爆发榜 Top 5">
        {exact.map((project) => (
          <ExactProjectCard key={project.githubRepositoryId} project={project} generationId={board.generationId} />
        ))}
      </section>

      <PendingFacts board={board} />
    </>
  );
}

function PendingFacts({ board }: { board: Extract<ExplosionBoardLoadResult, { kind: 'published' }>['board'] }) {
  const pending = board.pendingRanked.slice(0, 3);
  return (
    <>
      <div className={styles.sectionHeading}>
        <div>
          <h2>新入榜待验证</h2>
          <p>首次发现立即展示，但不进入精确 Top 5。</p>
        </div>
      </div>
      <section className={styles.pendingGrid} aria-label="新入榜待验证项目">
        {pending.map((project) => (
          <PendingProjectCard key={project.githubRepositoryId} project={project} generationId={board.generationId} />
        ))}
      </section>

      <section className={styles.provenanceBar} aria-label="数据覆盖和 generation">
        <div><ShieldCheck size={18} /><span>覆盖 {board.coverage?.state === 'healthy' ? '健康' : '降级'}</span></div>
        <span>
          {board.window?.state === 'exact' ? '精确窗口' : '观察窗口'}{' '}
          {board.window ? `${formatTime(board.window.startedAt)} → ${formatTime(board.window.endedAt)}` : '未发布'}
        </span>
        <span>查询 {board.coverage?.successfulQueryCount ?? 0} 成功 / {board.coverage?.failedQueryCount ?? 0} 失败</span>
        <span>Metadata 失败 {board.coverage?.metadataFailureCount ?? 0}</span>
        <span>精确 {board.coverage?.exactCount ?? 0} · 待验证 {board.coverage?.pendingCount ?? 0} · 冲突 {board.conflictCount}</span>
        <span>{board.dataLabel}</span>
        <code>{board.generationId}</code>
      </section>
    </>
  );
}

function ExactProjectCard({ project, generationId }: { project: ExactExplosionProject; generationId: string }) {
  return (
    <article className={styles.rankingCard}>
      <div className={styles.rank}>#{project.rank}</div>
      <div className={styles.projectIdentity}>
        <a href={project.htmlUrl} target="_blank" rel="noreferrer" className={styles.repository}>
          <FolderGit2 size={18} aria-hidden="true" /> {project.repository} <ArrowUpRight size={15} aria-hidden="true" />
        </a>
        <p className={styles.projectDescription}>{project.description || 'GitHub 暂未提供项目简介。'}</p>
        <div className={styles.tags}>
          {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
          {project.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
          {project.archived && <span>Archived</span>}
          {project.fork && <span>Fork</span>}
          {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
          <span>事实 · {project.state === 'exact_window' ? '精确 24h' : project.state}</span>
        </div>
        <RardarProjectExplanation repository={project.repository} generationId={generationId} />
      </div>
      <div className={styles.starFacts}>
        <strong>+{formatNumber(project.observedStarDelta)}</strong>
        <span><Star size={14} aria-hidden="true" /> {formatNumber(project.totalStars)} total</span>
      </div>
    </article>
  );
}

function PendingProjectCard({ project, generationId }: { project: PendingExplosionProject; generationId: string }) {
  const observed = project.observedWindowHours === null
    ? '等待第二个观察点'
    : `${project.observedWindowHours}h ${formatSigned(project.observedWindowStarDelta)}`;
  return (
    <article className={styles.pendingCard}>
      <span className={styles.pendingBadge}>待验证 #{project.pendingRank}</span>
      <a href={project.htmlUrl} target="_blank" rel="noreferrer">{project.repository}</a>
      <p className={styles.pendingDescription}>{project.description || 'GitHub 暂未提供项目简介。'}</p>
      <strong><Star size={14} aria-hidden="true" /> {formatNumber(project.totalStars)}</strong>
      <p>{observed}</p>
      <small>首次发现 {formatTime(project.firstSeenAt)}</small>
      <RardarProjectExplanation repository={project.repository} generationId={generationId} />
    </article>
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

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatSigned(value: number | null) {
  if (value === null) return '增量待确认';
  return `${value >= 0 ? '+' : ''}${formatNumber(value)} Star`;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}
