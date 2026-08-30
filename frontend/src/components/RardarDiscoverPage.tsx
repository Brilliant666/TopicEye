import Link from 'next/link';
import {
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
  type DiscoverLoadResult,
  type DiscoverResponse,
  type DiscoverStage,
} from '@/lib/rardar-discover';
import styles from './RardarFoundation.module.css';

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
    description: '最近一至两个 Observation 中首次出现。',
  },
  {
    key: 'rising',
    stage: 'rising',
    title: '持续升温',
    description: '已连续出现，并在实际观察窗口内获得正 Star 增量。',
  },
  {
    key: 'nearValidation',
    stage: 'near_validation',
    title: '接近验证',
    description: '已经积累接近 24 小时的观察证据，但尚未进入 Today 精确榜。',
  },
];

export default function RardarDiscoverPage({ result }: { result: DiscoverLoadResult }) {
  if (result.kind !== 'published') {
    return (
      <div className={`${styles.page} ${styles.discoverRealtimePage}`} data-rardar-route="/discover">
        <DiscoverHero board={null} />
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
  return (
    <div className={`${styles.page} ${styles.discoverRealtimePage}`} data-rardar-route="/discover">
      <DiscoverHero board={board} />
      <div className={styles.discoverStageFlow}>
        {SECTIONS.map((section) => (
          <DiscoverSection
            key={section.key}
            title={section.title}
            description={section.description}
            stage={section.stage}
            projects={board.stages[section.key]}
            generation={board.generation || ''}
          />
        ))}
      </div>
      <Coverage board={board} />
    </div>
  );
}

function DiscoverHero({ board }: { board: DiscoverResponse | null }) {
  return (
    <section className={styles.discoverRealtimeHero} data-testid="discover-hero">
      <div>
        <p className={styles.eyebrow}>Discover · Near real-time</p>
        <h1>发现刚刚开始升温的项目</h1>
        <p>
          来自 Rardar 每 2 小时一次的已验证 Observation。这里只展示实际观察窗口，
          尚未形成完整 24 小时精确排名，也不会外推日增量。
        </p>
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
}: {
  title: string;
  description: string;
  stage: DiscoverStage;
  projects: DiscoverCard[];
  generation: string;
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
          <p>本次已验证 Observation 中没有符合该阶段条件的项目。</p>
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
  return (
    <article className={styles.discoverRealtimeCard} data-testid="discover-project-card">
      <div className={styles.discoverCardTopline}>
        <span>{stageLabel(project.stage)}</span>
        <small>{sourceLabel(project.sourceMode)}</small>
      </div>
      <h3>{project.repository}</h3>
      <p className={styles.discoverIdentity}>{project.identitySummaryZh}</p>
      <p className={styles.discoverPositioning}>{project.positioningZh}</p>
      <div className={styles.discoverCapabilityTags}>
        {project.capabilities.slice(0, 3).map((item) => <span key={`${item.title}-${item.detail}`}>{item.title}</span>)}
      </div>
      <dl className={styles.discoverCardFacts}>
        <div className={styles.discoverGrowthFact}>
          <dt>实际增长</dt>
          <dd>+{formatNumber(project.observedStarDelta)} <small>/ 实际 {formatHours(project.observedWindowHours)}</small></dd>
        </div>
        <div><dt>当前 Star</dt><dd><Star size={13} /> {formatNumber(project.totalStars)}</dd></div>
        <div><dt>首次发现</dt><dd>{formatTime(project.firstSeenAt)}</dd></div>
        <div><dt>连续观察</dt><dd>{project.consecutiveCaptureCount} 次 capture</dd></div>
      </dl>
      <div className={styles.discoverMetadata}>
        {project.language && <span>{project.language}</span>}
        {project.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
        {project.license && <span>{project.license}</span>}
        {project.isFork && <span><GitBranch size={11} /> Fork</span>}
        {project.isArchived && <span>Archived</span>}
      </div>
      <div className={styles.discoverCardActions}>
        <Link href={detailHref}>查看项目详情</Link>
        <a href={project.url} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={14} /></a>
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
        <span>成功查询 {coverage.querySuccessCount}</span>
        <span>失败查询 {coverage.queryFailureCount}</span>
        <span>Metadata failure {coverage.metadataFailureCount}</span>
        <span>排除 Today exact {coverage.excludedExactCount}</span>
        <span>冲突 {coverage.conflictCount}</span>
        <span>来源 capture {coverage.sourceCaptureCount}</span>
      </div>
      <p>这是多源候选召回与连续观察的覆盖，不代表 GitHub 全站绝对完整扫描。</p>
    </details>
  );
}

function stageLabel(value: DiscoverStage) {
  return { just_discovered: '刚刚发现', rising: '持续升温', near_validation: '接近验证' }[value];
}

function sourceLabel(value: DiscoverCard['sourceMode']) {
  return { official_zh: '官方中文', official_translated: '官方资料译', rardar_derived: 'Rardar 整理' }[value];
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatHours(value: number) {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} 小时`;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}
