import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  ExternalLink,
  FileSearch,
  Gauge,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
} from 'lucide-react';

import {
  assertPublishableProject,
  type CapabilitySourceMode,
  narrativeSourceLabel,
  positioningSourceLabel,
  type ProjectCapability,
  type ProjectDetail,
} from '@/lib/rardar-intelligence';
import type { DiscoverProjectDetail } from '@/lib/rardar-discover';
import { beijingTime, boardPeriodLabel, boardTime, safeSourceUrl, type TrendingDetail } from '@/lib/rardar-trending';
import styles from './RardarFoundation.module.css';
import RardarProjectExplanation from './RardarProjectExplanation';
import RardarGrowthFacts from './RardarGrowthFacts';
import { HistoricalContext } from './RardarTrendingPage';

export default function RardarProjectDetailPage({ detail, historical = false }: { detail: ProjectDetail | DiscoverProjectDetail | TrendingDetail; historical?: boolean }) {
  const trendingDetail = 'repository' in detail ? detail : null;
  const discoverDetail = 'facts' in detail ? detail : null;
  const todayDetail = 'project' in detail ? detail : null;
  const isDiscover = discoverDetail !== null;
  const savedProfile = trendingDetail ? trendingDetail.displayProfile : (detail as ProjectDetail | DiscoverProjectDetail).profile;
  // These are render defaults for absent sections, never a synthesized Profile
  // or replacement identity/evidence/generation used for analysis.
  const profile = {
    ...savedProfile,
    originalDescription: savedProfile?.originalDescription || trendingDetail?.description,
    productFormsZh: savedProfile?.productFormsZh || [],
    supportedEnvironmentsZh: savedProfile?.supportedEnvironmentsZh || [],
    deliveryFormsZh: savedProfile?.deliveryFormsZh || [],
    positioningEvidenceRefs: savedProfile?.positioningEvidenceRefs || [],
    positioningExcludedClauses: savedProfile?.positioningExcludedClauses || [],
    coreValueEvidenceRefs: savedProfile?.coreValueEvidenceRefs || [],
    capabilities: savedProfile?.capabilities || [],
    officialHighlights: savedProfile?.officialHighlights || [],
    rardarAssessmentEvidenceRefs: savedProfile?.rardarAssessmentEvidenceRefs || [],
    rardarDifferentiators: savedProfile?.rardarDifferentiators || [],
    keyDifferentiators: savedProfile?.keyDifferentiators || [],
    primaryUseCasesZh: savedProfile?.primaryUseCasesZh || [],
    startHere: savedProfile?.startHere || [],
    selectedSections: savedProfile?.selectedSections || [],
    originalExcerpts: savedProfile?.originalExcerpts || [],
  };
  const project = trendingDetail
    ? { githubRepositoryId: trendingDetail.githubRepositoryId, repository: trendingDetail.repository, htmlUrl: `https://github.com/${trendingDetail.repository}`, primaryLanguage: trendingDetail.language, topics: trendingDetail.topics || [], licenseSpdxId: trendingDetail.license }
    : discoverDetail
    ? {
        githubRepositoryId: discoverDetail.facts.githubRepositoryId,
        repository: discoverDetail.facts.repository,
        htmlUrl: discoverDetail.facts.url,
        primaryLanguage: discoverDetail.facts.language,
        topics: discoverDetail.facts.topics,
        licenseSpdxId: discoverDetail.facts.license,
      }
    : todayDetail!.project;
  if (discoverDetail) {
    assertPublishableProject(discoverDetail.profile, true);
  } else if (todayDetail && todayDetail.schemaVersion >= 5 && todayDetail.schemaVersion < 8) {
    const requireIncludedRoles = todayDetail.schemaVersion >= 6;
    assertPublishableProject(todayDetail.project, requireIncludedRoles);
    assertPublishableProject(todayDetail.profile, requireIncludedRoles);
  }
  const relativeGrowth = todayDetail && todayDetail.project.baselineStars > 0
    ? todayDetail.project.observedStarDelta / todayDetail.project.baselineStars
    : null;
  const generationId = trendingDetail ? trendingDetail.generationId || 'history' : discoverDetail ? discoverDetail.discoverGenerationId : todayDetail!.generationId;
  const findHref = `/find?repositoryUrl=${encodeURIComponent(project.htmlUrl)}`;
  const sourceLabel = profile.officialNarrativeMode ? narrativeSourceLabel(profile.officialNarrativeMode) : '资料暂未补齐';
  const positioningLabel = profile.positioningSourceMode ? positioningSourceLabel(profile.positioningSourceMode) : '已保存项目档案';
  const primaryLinks = profile.startHere.slice(0, 4);
  const moreLinks = profile.startHere.slice(4);
  const presentedCapabilities = profile.capabilities;

  return (
    <div className={`${styles.page} ${styles.detailPage}`} data-rardar-route="/project">
      <nav className={styles.breadcrumb} aria-label="面包屑">
        <Link href={historical ? '/historical-hot' : isDiscover ? '/discover' : '/'}><ArrowLeft size={14} /> {historical ? '历史回顾' : isDiscover ? '发现' : '今日热榜'}</Link><span>/</span><span>{project.repository}</span>
      </nav>

      <section className={styles.detailHero} data-testid="project-identity-hero">
        <div className={styles.detailHeroCopy}>
          <div className={styles.detailEyebrow}><ShieldCheck size={15} /> 静态项目档案 · {trendingDetail ? materialLabel(trendingDetail.materialState) : todayDetail?.schemaVersion === 8 ? materialLabel(profile.materialState) : sourceLabel}</div>
          <h1>{project.repository}</h1>
          {profile.officialTaglineZh ? (
            <p className={styles.officialTagline} data-testid="detail-official-tagline">{profile.officialTaglineZh}</p>
          ) : profile.identitySummaryZh || profile.officialSummaryZh ? (
            <p className={styles.detailSafeIdentity}>{profile.identitySummaryZh || profile.officialSummaryZh}</p>
          ) : profile.originalDescription ? (
            <p className={styles.detailSafeIdentity}><small>原始介绍 · </small>{profile.originalDescription}</p>
          ) : (
            <p>项目介绍暂未补齐，仓库与榜单事实仍可查看。</p>
          )}
          <div className={styles.profileSignalGrid} aria-label="项目形态、环境与交付形式">
            <ProfileSignal label="产品形态" values={profile.productFormsZh} />
            <ProfileSignal label="适用环境" values={profile.supportedEnvironmentsZh} />
            <ProfileSignal label="交付形式" values={profile.deliveryFormsZh} />
          </div>
          <div className={styles.tags}>
            {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
            {project.topics.slice(0, 4).map((topic) => <span key={topic}>{topic}</span>)}
            {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
            <span>{trendingDetail ? materialLabel(trendingDetail.materialState) : todayDetail?.schemaVersion === 8 ? materialLabel(profile.materialState) : qualityLabel(profile.qualityState)}</span>
            {trendingDetail?.dualListed && !historical && <span>双榜上榜</span>}
          </div>
          <div className={styles.detailActions}>
            <a href={project.htmlUrl} target="_blank" rel="noreferrer">打开 GitHub <ArrowUpRight size={15} /></a>
            <Link href={findHref}>用这个仓库评估我的需求 <ArrowRight size={15} /></Link>
          </div>
        </div>
        {trendingDetail ? <TrendingHeroFacts detail={trendingDetail} historical={historical} /> : discoverDetail ? (
          <dl className={styles.heroFactPair} aria-label="发现核心事实">
            <Fact label="发现阶段" value={discoverStageLabel(discoverDetail.facts.stage)} />
            <Fact label="实际增长" value={`+${formatNumber(discoverDetail.facts.observedStarDelta)} / ${formatHours(discoverDetail.facts.observedWindowHours)}`} accent />
          </dl>
        ) : (
          <dl className={styles.heroFactPair} aria-label="今日核心事实">
            <Fact label="今日排名" value={`#${todayDetail!.project.rank}`} />
            <Fact label="24h 新增" value={`+${formatNumber(todayDetail!.project.observedStarDelta)}`} accent />
          </dl>
        )}
      </section>

      <div className={styles.detailFlow} data-testid="project-detail-flow">
        {discoverDetail && <DiscoverFactContext detail={discoverDetail} />}

        {profile.coreValueZh && <section className={styles.detailCoreValue} data-testid="project-core-value">
          <div className={styles.sectionKicker}><Sparkles size={16} /> 核心价值 · Rardar 解读</div>
          <h2>{profile.coreValueZh}</h2>
          <EvidenceBadges values={profile.coreValueEvidenceRefs} />
        </section>}
        {profile.positioningZh && profile.positioningZh !== profile.coreValueZh && <section className={profile.coreValueZh ? styles.detailPositioning : styles.detailCoreValue} data-testid="project-official-positioning">
          <div className={styles.sectionKicker}><BookOpen size={16} /> 项目定位 · {positioningLabel}</div>
          <p>{profile.positioningZh}</p>
          <EvidenceBadges values={profile.positioningEvidenceRefs} />
        </section>}
        {!profile.coreValueZh && !profile.positioningZh && <p className={styles.projectDescription}>核心定位暂未补齐，可先查看真实上榜资料和原仓库。</p>}

        {presentedCapabilities.length > 0 ? (
          <DetailSection
            icon={Boxes}
            title="它能做什么"
            subtitle="能力来自同一份已验证项目档案；来源类型与仓库证据逐项标明。"
          >
            <ol className={styles.capabilityNarrative} data-testid="project-capability-section">
              {presentedCapabilities.map((capability, index) => (
                <li
                  key={`${capability.title}-${capability.detail}`}
                  data-testid="project-capability-item"
                  data-source-mode={capability.sourceMode || 'rardar_derived'}
                >
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div><strong>{capability.title}</strong><p>{capability.detail}</p><CapabilityEvidence capability={capability} legacyProfile={profile} /></div>
                </li>
              ))}
            </ol>
          </DetailSection>
        ) : <p>能力资料暂未补齐；可前往原仓库核对。</p>}

        <section className={styles.adoptionLayer} data-testid="rardar-adoption-layer">
          <div className={styles.adoptionIntro}>
            <div className={styles.sectionKicker}><Gauge size={16} /> Rardar 决策与采用</div>
            <h2>从“看懂项目”进入“是否值得复用”</h2>
            <p>AI 只分析差异、可复用资产、成本、适合场景和落地边界；项目身份、官方能力与{trendingDetail ? '来源榜单记录' : isDiscover ? '发现阶段和事实顺序' : '今日名次'}不由模型改写。读取资料不代表已经运行验证。</p>
            {profile.rardarAssessmentZh && profile.rardarAssessmentZh !== profile.coreValueZh && (
              <div className={styles.rardarAssessment} data-testid="rardar-assessment">
                <span>Rardar 判断</span>
                <strong>{profile.rardarAssessmentZh}</strong>
                <EvidenceBadges values={profile.rardarAssessmentEvidenceRefs} />
              </div>
            )}
            {(profile.rardarDifferentiators.length > 0 || profile.keyDifferentiators.length > 0) && (
              <div className={styles.rardarDifferentiatorGrid} aria-label="Rardar 关键差异">
                {(profile.rardarDifferentiators.length ? profile.rardarDifferentiators : profile.keyDifferentiators).map((item) => (
                  <Differentiator key={`${item.title}-${item.detail}`} item={item} />
                ))}
              </div>
            )}
            {profile.primaryUseCasesZh.length > 0 && (
              <div className={styles.useCaseStrip} aria-label="适合场景">
                <Target size={16} />
                <span>{profile.primaryUseCasesZh.join(' · ')}</span>
              </div>
            )}
            <p className={styles.findDecisionHint}>已有明确需求时，可从页面顶部进入 Find，核对匹配、缺口与未知条件。</p>
          </div>
          <div className={styles.adoptionAction}>
            <RardarProjectExplanation
              repository={project.repository}
              githubRepositoryId={project.githubRepositoryId ?? undefined}
              stableId={trendingDetail?.projectId}
              generationId={generationId}
              source={trendingDetail ? historical ? 'historical_hot' : 'trending' : isDiscover ? 'discover' : 'today'}
            />
          </div>
        </section>

        {primaryLinks.length > 0 && (
          <DetailSection icon={FileSearch} title="如何开始" subtitle="先看最有助于理解和采用的四个入口，其余资料按需展开。">
            <div className={styles.startHerePrimary}>
              {primaryLinks.map((item, index) => (
                <a key={item.path} href={item.htmlUrl} target="_blank" rel="noreferrer">
                  <span className={styles.startHereIndex}>{index + 1}</span>
                  <span><strong>{item.label}</strong><small>{startHereReason(item.label)}</small><code>{item.path}</code></span>
                  <ExternalLink size={14} />
                </a>
              ))}
            </div>
            {moreLinks.length > 0 && (
              <details className={styles.moreResources}>
                <summary>更多官方资料（{moreLinks.length}）</summary>
                <div>
                  {moreLinks.map((item) => (
                    <a key={item.path} href={item.htmlUrl} target="_blank" rel="noreferrer">
                      <span>{item.label}</span><code>{item.path}</code><ExternalLink size={13} />
                    </a>
                  ))}
                </div>
              </details>
            )}
          </DetailSection>
        )}

        {profile.positioningExcludedClauses.length > 0 && <DetailSection icon={FileSearch} title="使用与边界补充" subtitle="保留资料中的部署、操作和限制说明，不把未验证条件写成已完成验证。">
          <div className={styles.rardarDifferentiatorGrid}>{profile.positioningExcludedClauses.map(item => <article key={`${item.role}-${item.text}`}><strong>{{ operation: '使用方式', deployment: '部署条件', validation: '验证说明', example: '使用示例', boundary: '限制与边界' }[item.role]}</strong><p>{item.text}</p><EvidenceBadges values={item.evidenceRefs} /></article>)}</div>
        </DetailSection>}

        {trendingDetail && <TrendingFactContext detail={trendingDetail} historical={historical} />}
        {todayDetail && (
          <section className={styles.observationFacts} data-testid="project-observation-facts">
            <header><Star size={17} /><div><h2>24 小时事实</h2><p>Hero 已给出结果，这里补充基线、窗口与覆盖，不重复名次和增量。</p></div></header>
            <dl>
              <Fact label="基线 Star" value={formatNumber(todayDetail!.project.baselineStars)} />
              <Fact label="当前 Star" value={formatNumber(todayDetail!.project.totalStars)} />
              <Fact label="相对增长" value={relativeGrowth === null ? '—' : `${(relativeGrowth * 100).toFixed(1)}%`} />
              <Fact label="窗口开始" value={formatTime(todayDetail!.project.windowStartedAt)} />
              <Fact label="窗口结束" value={formatTime(todayDetail!.project.windowEndedAt)} />
              <Fact label="覆盖状态" value={todayDetail!.coverage?.state === 'degraded' ? '部分来源降级' : '覆盖健康'} />
            </dl>
            {todayDetail!.coverage?.state === 'degraded' && (
              <p className={styles.coverageNote}>本轮仍按已验证事实排序；{coverageReason(todayDetail!.coverage.metadataFailureCount, todayDetail!.conflictCount)}。</p>
            )}
          </section>
        )}

        <details className={styles.provenanceDetails} data-testid="official-evidence">
          <summary><BookOpen size={16} /> 来源、官方原文与审计 <span>按需查看</span></summary>
          <div className={styles.provenanceDetailsBody}>
            <dl className={styles.sourceFacts}>
              <div><dt>叙事模式</dt><dd>{profile.officialNarrativeMode || '尚无有效解读'}</dd></div>
              <div><dt>叙事来源</dt><dd>{sourceLabel}</dd></div>
              <div><dt>核心定位来源</dt><dd>{positioningLabel}</dd></div>
              <div><dt>官方重点</dt><dd>{profile.officialHighlights.length} 项</dd></div>
              <div><dt>Rardar 判断来源</dt><dd>{profile.rardarAssessmentZh ? '独立分析层' : '未生成'}</dd></div>
              <div><dt>来源</dt><dd>{profile.sourceLabel || '尚无有效项目档案'}</dd></div>
              <div><dt>README</dt><dd>{profile.readmePath || '未取得'}</dd></div>
              <div><dt>Revision</dt><dd><code>{profile.readmeBlobSha || 'GitHub Description'}</code></dd></div>
              <div><dt>翻译状态</dt><dd>{translationLabel(profile.translationState)}</dd></div>
              <div><dt>Profile 质量</dt><dd>{qualityLabel(profile.qualityState)}</dd></div>
              {profile.generatedAt && (
                <div><dt>已保存资料时间</dt><dd>{formatTime(profile.generatedAt)}</dd></div>
              )}
              <div><dt>{isDiscover ? 'Discover Generation' : 'Generation'}</dt><dd><code>{generationId}</code></dd></div>
              {!trendingDetail && <div><dt>Serving</dt><dd><code>{(detail as ProjectDetail | DiscoverProjectDetail).servingGenerationId}</code></dd></div>}
              {trendingDetail?.material?.sourceGeneration && <div><dt>资料来源版本</dt><dd><code>{trendingDetail.material.sourceGeneration}</code></dd></div>}
              <div><dt>Evidence</dt><dd><code>{profile.evidenceDigest || '尚无项目档案证据'}</code></dd></div>
            </dl>
            {profile.selectedSections.length > 0 && <p className={styles.sourceSections}>来源章节：{profile.selectedSections.map((section) => section.heading).join(' · ')}</p>}
            {profile.originalExcerpts.length > 0 && (
              <div className={styles.officialExcerpts}>
                <h3>官方原文摘录</h3>
                {profile.originalExcerpts.map((excerpt) => <blockquote key={excerpt}>{excerpt}</blockquote>)}
              </div>
            )}
          </div>
        </details>
      </div>
    </div>
  );
}

function TrendingHeroFacts({ detail, historical }: { detail: TrendingDetail; historical: boolean }) {
  const github = detail.appearances.find(item => item.source === 'github');
  const trendshift = detail.appearances.find(item => item.source === 'trendshift');
  return <div className={styles.trendingHeroFacts} aria-label={historical ? '历史上榜事实' : '双榜来源事实'}><dl className={styles.sourceRankFacts}>
    {historical ? <div><HistoricalContext project={detail} /></div> : <>
      {github && <Fact label="GitHub Trending" value={`#${github.rank}`} />}
      {trendshift && <Fact label="Trendshift 日榜" value={`#${trendshift.rank}`} />}
    </>}
    </dl><RardarGrowthFacts project={detail} historical={historical} />
  </div>;
}

function TrendingFactContext({ detail, historical }: { detail: TrendingDetail; historical: boolean }) {
  return <section className={styles.observationFacts} data-testid="project-trending-facts">
    <header><Star size={17} /><div><h2>{historical ? '历史上榜依据' : '来源榜单事实'}</h2><p>名次与指标保留各来源语义；资料解读不改变榜单事实。</p></div></header>
    <dl>
      {detail.appearances.map(item => <Fact key={`${item.source}-${item.sourceDate}-${item.fetchedAt}`} label={`${item.source === 'github' ? 'GitHub Trending' : 'Trendshift'} 日榜`} value={`#${item.rank} · ${boardPeriodLabel(item)} · 成功采集 ${beijingTime(item.fetchedAt)}`} />)}
      {historical && detail.firstSeenAt && <Fact label="本地最早采集" value={boardTime(detail.firstSeenAt)} />}
      {detail.displayProfile?.generatedAt && <Fact label="项目资料生成时间" value={boardTime(detail.displayProfile.generatedAt)} />}
      {detail.primaryGrowth && <Fact label="主增长统计口径" value={detail.primaryGrowth.source === 'rardar_history' ? `${boardTime(detail.primaryGrowth.windowStartedAt)} → ${boardTime(detail.primaryGrowth.windowEndedAt)}` : detail.primaryGrowth.reportedDeltaPeriod || detail.primaryGrowth.trendshiftMetricPeriod || '来源日榜，未声明精确窗口'} />}
      {detail.totalStarsSource && <Fact label="累计 Star 来源" value={`${detail.totalStarsSource.source === 'github' ? 'GitHub Trending' : 'Trendshift'} · 采集 ${boardTime(detail.totalStarsSource.fetchedAt)}`} />}
      {detail.metadataSource && <Fact label="语言、主题和许可证" value={`GitHub 仓库元数据 · 读取 ${boardTime(detail.metadataSource.fetchedAt)}`} />}
    </dl>
    {detail.historicalEvidence?.map(item => <p className={styles.projectDescription} key={item.sourceUrl}>GitHub 历史上榜 {item.reportedAppearanceCount} 次（来源报告，具体日期未知），采集 {boardTime(item.fetchedAt)}。{safeSourceUrl(item.sourceUrl) && <a href={safeSourceUrl(item.sourceUrl)} target="_blank" rel="noopener noreferrer"> 核对来源 ↗</a>}</p>)}
    {detail.historicalRardarEvidence?.map(item => <p className={styles.projectDescription} key={`${item.sourceGeneration}-${item.rank}`}>Rardar 历史榜 #{item.rank} · 原观察窗口 {boardTime(item.windowStartedAt)} → {boardTime(item.windowEndedAt)} · 当时观测新增 {formatNumber(item.observedStarDelta)} Star · 当时累计 {formatNumber(item.totalStars)} Star。{detail.githubRepositoryId !== null && <Link href={`/project/github/${detail.githubRepositoryId}?generation=${encodeURIComponent(item.sourceGeneration)}`}> 查看原榜资料 →</Link>}</p>)}
  </section>;
}

function DiscoverFactContext({ detail }: { detail: DiscoverProjectDetail }) {
  const facts = detail.facts;
  return (
    <section className={styles.observationFacts} data-testid="project-discover-facts">
      <header>
        <Star size={17} />
        <div>
          <h2>为什么现在出现在发现？</h2>
          <p>{discoverReason(detail)} 全部为实际 Observation，不折算或外推 24 小时增长。</p>
        </div>
      </header>
      <dl>
        <Fact label="发现阶段" value={discoverStageLabel(facts.stage)} />
        {facts.eligibilityClass && <Fact label="候选资格" value={facts.eligibilityClass === 'exact_outside_published' ? '完整 24h 事实 · Today Top 20 榜外' : '尚未形成完整 24h exact'} />}
        <Fact label="产品分类" value={discoverCategoryLabel(detail.category)} />
        {facts.stage === 'outside_today_momentum' && <Fact label="Today 发布边界" value={`Top ${detail.todayPublishedTopCount ?? 20}`} />}
        {facts.stage === 'outside_today_momentum' && <Fact label="Today exact 排名" value={`#${facts.todayExactRank ?? '—'}`} />}
        {facts.stage === 'outside_today_momentum' && <Fact label="Today 完整 24h 增量" value={`+${formatNumber(facts.todayExact24hDelta ?? 0)} Star`} />}
        {facts.stage === 'outside_today_momentum' && <Fact label={`最近实际 ${formatHours(facts.recentWindowHours ?? 0)}`} value={`+${formatNumber(facts.recentObservedStarDelta ?? 0)} Star`} accent />}
        {facts.stage === 'outside_today_momentum' && <Fact label="前一可比窗口" value={signedStar(facts.priorComparableWindowDelta)} />}
        {facts.stage === 'outside_today_momentum' && <Fact label="短窗口加速" value={signedStar(facts.accelerationDelta)} />}
        <Fact label="首次发现" value={formatTime(facts.firstSeenAt)} />
        <Fact label="最新观察" value={formatTime(facts.lastObservedAt)} />
        <Fact label="实际窗口" value={formatHours(facts.observedWindowHours)} />
        <Fact label="实际增量" value={`+${formatNumber(facts.observedStarDelta)}`} />
        <Fact label="当前 Star" value={formatNumber(facts.totalStars)} />
        <Fact label="Capture 数" value={String(facts.captureCount)} />
        <Fact label="连续 Capture" value={`${facts.consecutiveCaptureCount} 次`} />
        <Fact label="正增长区间" value={facts.positiveIntervalCount == null ? 'v1 Artifact 未提供' : `${facts.positiveIntervalCount} 个`} />
        <Fact label="最长连续正增长" value={facts.consecutivePositiveIntervalCount == null ? 'v1 Artifact 未提供' : `${facts.consecutivePositiveIntervalCount} 个区间`} />
        <Fact label="最新区间增量" value={facts.latestIntervalDelta == null ? '尚无有效连续区间' : `${facts.latestIntervalDelta >= 0 ? '+' : ''}${formatNumber(facts.latestIntervalDelta)} Star`} />
        <Fact label="下一次 Observation" value={detail.nextExpectedAt ? formatTime(detail.nextExpectedAt) : '等待下一次 Serving'} />
        <Fact label="下一次 Today 结算" value={detail.nextTodaySettlementAt ? formatTime(detail.nextTodaySettlementAt) : '等待下一次 Serving'} />
        <Fact label="为什么尚未进入 Today" value={todayReasonLabel(detail.todayReason)} />
        <Fact label="覆盖状态" value={detail.coverage.state === 'degraded' ? '部分来源降级' : '覆盖健康'} />
      </dl>
      <p className={styles.discoverContextBoundary}>
        这里是 DiscoverFactContext；项目身份、定位、能力和证据继续复用同一份 canonical ProjectProfile。
      </p>
      {detail.coverage.state === 'degraded' && (
        <p className={styles.coverageNote}>本轮仍保持 Artifact 阶段与事实顺序；{coverageReason(detail.coverage.metadataFailureCount, detail.conflictCount)}。</p>
      )}
    </section>
  );
}

function ProfileSignal({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return <div><span>{label}</span><strong>{values.join(' · ')}</strong></div>;
}

function Differentiator({ item }: { item: ProjectCapability }) {
  return <article><strong>{item.title}</strong><p>{item.shortDetail || item.detail}</p><EvidenceBadges values={item.evidenceRefs} /></article>;
}

function EvidenceBadges({ values }: { values: string[] }) {
  if (values.length === 0) return null;
  const counts = new Map<string, number>();
  values.forEach((value) => {
    const label = evidenceSourceLabel(value);
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return <small className={styles.capabilityEvidence}>{Array.from(counts, ([label, count]) => count > 1 ? `${label} · ${count}处证据` : label).join(' · ')}</small>;
}

function CapabilityEvidence({
  capability,
  legacyProfile,
}: {
  capability: ProjectCapability;
  legacyProfile: Partial<ProjectDetail['profile']>;
}) {
  const labels = Array.from(new Set(capability.evidenceRefs.map(evidenceSourceLabel)));
  const sourceMode = capability.sourceMode || legacyCapabilitySourceMode(capability, legacyProfile);
  return (
    <small className={styles.capabilityEvidence}>
      来源：{capabilitySourceLabel(sourceMode)} · 证据：{labels.join(' · ')}
    </small>
  );
}

function legacyCapabilitySourceMode(
  capability: ProjectCapability,
  profile: Partial<ProjectDetail['profile']>,
): CapabilitySourceMode {
  const matchesOfficialHighlight = profile.officialHighlights?.some((highlight) => (
    highlight.titleZh === capability.title
    && highlight.detailZh === capability.detail
    && highlight.evidenceRefs.join('\u0000') === capability.evidenceRefs.join('\u0000')
  ));
  if (matchesOfficialHighlight && profile.officialNarrativeMode === 'official_zh') return 'official_zh';
  if (matchesOfficialHighlight && profile.officialNarrativeMode === 'official_translated') return 'official_translated';
  return 'rardar_derived';
}

function materialLabel(state: string | undefined) {
  return state === 'complete' ? '资料完整' : state === 'partial' ? '资料部分可用' : '资料暂未补齐';
}

function capabilitySourceLabel(mode: CapabilitySourceMode | null | undefined) {
  return {
    official_zh: '官方中文 README',
    official_translated: '官方 README（译）',
    rardar_derived: 'Rardar 整理',
    deterministic_fallback: 'Rardar 整理',
  }[mode || 'rardar_derived'];
}

function evidenceSourceLabel(value: string) {
  if (value === 'description') return 'GitHub Description';
  if (value.startsWith('readme:')) return '官方 README';
  if (value.startsWith('documented-path:')) return 'README 路径';
  if (value.startsWith('path:')) return '仓库目录';
  return '官方仓库证据';
}

function coverageReason(metadataFailures: number, conflicts: number) {
  const reasons = [];
  if (metadataFailures > 0) reasons.push(`${metadataFailures} 个 metadata failure`);
  if (conflicts > 0) reasons.push(`${conflicts} 个负增长冲突`);
  return reasons.length > 0 ? reasons.join('，') : '少量候选来源不可用';
}

function Fact({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div><dt>{label}</dt><dd className={accent ? styles.factAccent : undefined}>{value}</dd></div>;
}

function DetailSection({ icon: Icon, title, subtitle, children }: { icon: typeof BookOpen; title: string; subtitle: string; children: ReactNode }) {
  return <section className={styles.detailSection}><header><span><Icon size={18} /></span><div><h2>{title}</h2><p>{subtitle}</p></div></header><div className={styles.detailSectionBody}>{children}</div></section>;
}

function startHereReason(label: string) {
  if (label.includes('快速开始') || label.includes('安装')) return '先确认安装、运行和最短验证路径';
  if (label.includes('定位') || label.includes('介绍')) return '先建立项目边界与用途认知';
  if (label.includes('能力') || label.includes('特性')) return '核对核心能力是否覆盖你的任务';
  if (label.includes('实现') || label.includes('架构')) return '理解关键机制与工程边界';
  return '查看与采用判断最相关的官方资料';
}

function qualityLabel(value: ProjectDetail['profile']['qualityState'] | undefined) {
  return value ? { ready: '档案可用', partial: '档案部分可用', rejected: '低质量内容已隔离' }[value] : '资料暂未补齐';
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}

function discoverStageLabel(value: DiscoverProjectDetail['facts']['stage']) {
  return {
    just_discovered: '刚刚发现',
    outside_today_momentum: '榜外异动',
    rising: '持续升温',
    near_validation: '待日榜验证',
  }[value];
}

function discoverReason(detail: DiscoverProjectDetail) {
  const facts = detail.facts;
  if (facts.stage === 'just_discovered') {
    return '最近 4 小时首次进入候选池，当前只确认新召回事实，尚未形成增长结论。';
  }
  if (facts.stage === 'rising') {
    const intervals = facts.consecutivePositiveIntervalCount == null
      ? '连续 Observation'
      : `连续 ${facts.consecutivePositiveIntervalCount} 个观察区间`;
    return `${intervals}获得正增长，实际 ${formatHours(facts.observedWindowHours)}新增 ${formatNumber(facts.observedStarDelta)} Star。`;
  }
  if (facts.stage === 'outside_today_momentum') {
    return `该项目已形成完整 24 小时事实，Today exact 为 #${facts.todayExactRank ?? '—'}，未进入 Top ${detail.todayPublishedTopCount ?? 20}；最近 ${formatHours(facts.recentWindowHours ?? 0)}新增 ${formatNumber(facts.recentObservedStarDelta ?? 0)} Star，高于此前相同窗口的 ${formatNumber(facts.priorComparableWindowDelta ?? 0)} Star，并有 ${facts.consecutivePositiveIntervalCount ?? 0} 个连续正增长区间。`;
  }
  return `已持续观察 ${formatHours(facts.observedWindowHours)}并通过信号门禁，等待下一次 08:00 日榜结算。`;
}

function discoverCategoryLabel(value: DiscoverProjectDetail['category']) {
  if (!value) return '旧版 Serving 未分类';
  return {
    'ai-agent': 'AI 与 Agent',
    'dev-tools': '开发工具',
    'data-infra': '数据与基础设施',
    productivity: '生产力',
    'video-content': '视频与内容',
    other: '其他',
  }[value];
}

function todayReasonLabel(value: DiscoverProjectDetail['todayReason']) {
  return {
    new_candidate: '刚进入候选池，等待形成完整增长证据与日榜窗口。',
    awaiting_growth_evidence: '已出现连续增长，但尚未经过下一次每日 08:00 Today 结算。',
    awaiting_daily_settlement: '已通过信号门禁，正在等待下一次每日 08:00 Today 结算。',
    outside_today_top20_with_momentum: '已形成完整 24 小时事实，但 exact 排名位于 Today Top 20 之外；最近短窗口出现新的连续增长和加速。',
  }[value || 'new_candidate'];
}

function signedStar(value: number | null | undefined) {
  if (value == null) return '窗口证据不足';
  return `${value >= 0 ? '+' : ''}${formatNumber(value)} Star`;
}

function formatHours(value: number) {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} 小时`;
}

function translationLabel(value: ProjectDetail['profile']['translationState'] | undefined) {
  return value ? { not_needed: '官方中文原文', translated: '官方英文内容忠实翻译', pending: '待处理', unavailable: '未取得翻译' }[value] : '尚无中文解读';
}
