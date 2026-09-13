'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ArrowRight, ArrowUpRight, BookOpen, Clock3, FolderGit2, ShieldCheck, Sparkles } from 'lucide-react';
import RardarTodayOperations from './RardarTodayOperations';
import RardarGrowthFacts from './RardarGrowthFacts';
import { narrativeSourceLabel, positioningSourceLabel } from '@/lib/rardar-intelligence';
import { beijingTime, boardPeriodLabel, boardTime, introductionUnavailableText, projectLink, safeSourceUrl, totalStarsProvenance, type TrendingBoard, type TrendingProject } from '@/lib/rardar-trending';
import styles from './RardarFoundation.module.css';

export const boardSourceName = { github: 'GitHub Trending', trendshift: 'Trendshift' };

export function TrendingCard({ project, generationId, historical = false, index }: { project: TrendingProject; generationId: string; historical?: boolean; index?: number }) {
  const profile = project.displayProfile;
  const detailHref = projectLink(project.projectId, generationId, historical);
  const summary = profile?.officialTaglineZh || profile?.identitySummaryZh || profile?.officialSummaryZh || project.profile?.summary;
  const positioning = profile?.coreValueZh || profile?.positioningZh || project.profile?.positioning;
  const forms = profile?.productFormsZh || project.productForms || [];
  const sourceLabel = profile ? narrativeSourceLabel(profile.officialNarrativeMode) : project.profile?.sourceLabel;
  return <article className={styles.rankingCard} data-project-id={project.projectId}>
    <div className={styles.rank} aria-label="展示序号">{index === undefined ? <FolderGit2 size={24} /> : String(index + 1).padStart(2, '0')}</div>
    <div className={styles.projectIdentity}>
      <Link href={detailHref} className={styles.repository}><FolderGit2 size={18} aria-hidden="true" />{project.repository}<ArrowRight size={14} /></Link>
      {summary ? <p className={styles.officialTagline}>{summary}</p> : project.description ? <p className={styles.projectDescription}><small>原始介绍{!/[\u3400-\u9fff]/u.test(project.description) ? ' · 中文解读待补充' : ''} · </small>{project.description}</p> : <p className={styles.projectDescription}>{introductionUnavailableText(project)}</p>}
      {forms.length > 0 && <div className={styles.productForms} aria-label="产品形态">{forms.map(form => <span key={form}>{form}</span>)}</div>}
      {positioning && <section className={styles.officialPositioningBlock} aria-label={profile?.coreValueZh ? '核心价值' : '核心定位'} data-testid="today-official-positioning"><span>{profile?.coreValueZh ? '核心价值 · Rardar 解读' : `核心定位 · ${profile ? positioningSourceLabel(profile.positioningSourceMode) : '已保存解读'}`}</span><p>{positioning}</p></section>}
      <div className={styles.tags}>
        {project.language && <span>{project.language}</span>}{project.topics?.slice(0, 4).map(topic => <span key={topic}>{topic}</span>)}{project.license && <span>{project.license}</span>}
        {sourceLabel && <span>{sourceLabel}</span>}
        <span>{project.materialState === 'complete' ? '档案可用' : project.materialState === 'partial' ? '资料部分可用' : '资料暂未补齐'}</span>
        {project.dualListed && !historical && <span className={styles.dualBoardBadge}>双榜上榜</span>}
      </div>
      {historical ? <HistoricalContext project={project} /> : <div className={styles.boardAppearanceList}>{project.appearances.map(appearance => <span key={appearance.source}>{boardSourceName[appearance.source]} #{appearance.rank}</span>)}</div>}
      <details className={styles.provenanceDetails}><summary>{historical ? '历史记录' : '来源与更新时间'}</summary><div className={styles.provenanceDetailsBody}>
        {project.appearances.map(item => <p key={`${item.source}-${item.fetchedAt}`}>{boardSourceName[item.source]} #{item.rank} · {boardPeriodLabel(item)} · 成功采集 {beijingTime(item.fetchedAt)}{!historical && ` · ${item.source === 'github' ? item.reportedDeltaPeriod : item.trendshiftMetricPeriod}`}</p>)}
          {project.totalStarsSource && <p>累计 Star 来源：{totalStarsProvenance(project.totalStarsSource)}</p>}
          {project.metadataSource && <p>语言、主题和许可证：GitHub 仓库元数据 · 读取 {boardTime(project.metadataSource.fetchedAt)}</p>}
        {historical && project.historicalEvidence?.map(item => <p key={item.sourceUrl}>来源报告历史上榜 {item.reportedAppearanceCount} 次；具体日期未知，不等于本地逐日记录。{safeSourceUrl(item.sourceUrl) && <a href={safeSourceUrl(item.sourceUrl)} target="_blank" rel="noopener noreferrer">核对来源 ↗</a>}</p>)}
        {historical && project.historicalRardarEvidence?.map(item => <p key={item.sourceGeneration}>Rardar 历史榜 #{item.rank} · {boardTime(item.windowStartedAt)} → {boardTime(item.windowEndedAt)}</p>)}
      </div></details>
      <div className={styles.cardActions}><Link className={styles.findPrefillLink} href={detailHref}>查看项目详情 <ArrowRight size={14} /></Link><a className={styles.githubLink} href={`https://github.com/${project.repository}`} target="_blank" rel="noopener noreferrer">GitHub <ArrowUpRight size={14} /></a></div>
    </div>
    <RardarGrowthFacts project={project} historical={historical} />
  </article>;
}

export function HistoricalContext({ project }: { project: TrendingProject }) {
  const context = project.historicalContext;
  if (!context) return <p className={styles.projectDescription}>历史日期未取得</p>;
  if (context.kind === 'reported_count') return <p className={styles.projectDescription}>曾上 GitHub 日榜 · 具体日期未知</p>;
  return <p className={styles.projectDescription}>{context.kind === 'rardar' ? 'Rardar 历史榜' : boardSourceName[context.source as keyof typeof boardSourceName]} · {context.dateKind === 'capture' ? '采集于 ' : context.dateKind === 'window' ? '窗口结束 ' : '榜单日期 '}{boardTime(context.date)}</p>;
}

export default function RardarTrendingPage({ board, historical = false }: { board: TrendingBoard | null; historical?: boolean }) {
  const [visible, setVisible] = useState(20);
  const publishedAt = historical ? board?.dailyReview?.publishedAt : board?.publishedAt;
  const shownProjects = historical ? board?.projects : board?.projects.slice(0, visible);
  const minimumGrowth = board?.minimumDailyGrowth ?? 200;
  const noHealthySource = board?.sources.length && board.sources.every(source => source.status !== 'healthy');
  return <div className={`${styles.page} ${styles.todayPage}`} data-rardar-route={historical ? '/historical-hot' : '/'}>
    <section className={`${styles.hero} ${styles.todayHero}`} data-testid="today-hero"><div className={styles.heroContent}>
      <p className={styles.eyebrow}>{historical ? 'History · Project Review' : 'Today · Trending Repositories'}</p>
      <h1 className={`${styles.heroTitle} ${styles.trendingHeroTitle}`}><span className={styles.trendingSectionName}>{historical ? '历史回顾' : '今日热榜'}</span><span className={styles.heroTitleAccent}>{historical ? '认识曾经错过的好项目' : <><span className={styles.heroPhrase}>看见热门项目，</span><span className={styles.heroPhrase}>读懂它的价值</span></>}</span></h1>
      <p className={styles.heroDescription}>{historical ? '每天轮换一组已有可读介绍的历史项目，复用同一份项目档案与完整解读。历史关注与当前维护状态分别核对。' : 'GitHub Trending 与 Trendshift 自有日榜合并去重，按来源报告的 Star 增长降序排列，保留两榜原始名次；项目解读不参与排序。'}</p>
      <div className={styles.foundationNotice}><span className={styles.noticePill}><ShieldCheck size={15} /> 真实来源 · 原始名次</span><span className={styles.noticePill}><Sparkles size={15} /> 共享项目档案 · 按需深度解读</span></div>
    </div></section>
    <div className={styles.sectionHeading}><div><h2>{historical ? `本期回顾 · ${board?.projects.length ?? 0} 项` : '双榜项目清单'}</h2><p>{historical ? '每日稳定轮换，当天内容不重抽；展示序号不是热度排名。' : `展示来源报告日增长≥${minimumGrowth}的项目，双榜项目优先采用GitHub Trending。`}</p></div>{publishedAt && <span className={styles.timestamp}>{historical ? `回顾日期 ${board?.dailyReview?.date} · 发布` : '清单发布'} {boardTime(publishedAt)}</span>}</div>
    {!historical && board && <p className={styles.boardSourceSummary} aria-label="两源读取状态">{board.sources.map(source => <span key={source.source}>{source.label}：{source.status === 'healthy' ? '读取成功' : source.status === 'stale' ? '保留旧记录，待更新' : '读取失败'} · {source.sourceDate ? `源榜 ${source.sourceDate}${source.sourceTimezone ? `（${source.sourceTimezone}）` : ''}` : '源榜日期未知'} · 成功采集 {beijingTime(source.fetchedAt)}</span>)}</p>}
    {!board ? <section className={styles.emptyExactCard} role="status"><Clock3 size={28} /><div><h3>已保存清单暂时不可用</h3><p>请稍后重试；普通阅读不会触发采集或模型请求。</p></div></section> : <>
      <section className={styles.rankingList} aria-label={historical ? '历史回顾项目' : '双榜今日热榜'}>{shownProjects?.map((project, index) => <TrendingCard key={project.projectId} project={project} generationId={board.generationId} historical={historical} index={index} />)}</section>
      {board.projects.length === 0 && <section className={styles.emptyExactCard} role="status"><BookOpen size={28} /><p>{historical ? board.dailyReview ? '本期尚无具备可读介绍的历史项目，已有项目详情仍可访问。' : '尚未发布每日回顾，等待日程生成；普通阅读不会重新抽取项目。' : noHealthySource ? '来源暂不可用，暂时没有可展示的达标项目；来源恢复后继续更新。' : `本次有效来源中暂无日增长达到 ${minimumGrowth} 的项目。`}</p></section>}
      {!historical && visible < board.projects.length && <div className={styles.expandBoard}><button type="button" className={styles.boardLoadMore} onClick={() => setVisible(value => value + 20)}>加载更多（剩余 {board.projects.length - visible} 项）</button></div>}
      <details className={styles.provenanceDetails}><summary><BookOpen size={16} /> {historical ? '回顾批次与来源' : '来源与更新时间'} <span>{board.projects.length} {historical ? '个回顾项目' : '个达标项目'}</span></summary><div className={styles.provenanceDetailsBody}>
        {!historical && board.sources.map(source => <p key={source.source}><strong>{source.label}</strong> · {source.count} 项 · {boardPeriodLabel(source)} · {source.status === 'healthy' ? '读取成功' : source.status === 'stale' ? '保留旧记录，尚未取得应更新周期' : '来源暂不可用'} · 成功采集 {beijingTime(source.fetchedAt)} · 最近检查 {beijingTime(source.checkedAt)}</p>)}
        {!historical && <p>来源去重共 {board.rawProjectCount ?? board.projects.length} 项 · 达标 {board.eligibleProjectCount ?? board.projects.length} 项 · 主增长未知 {board.unknownGrowthCount ?? 0} 项。门槛不改变原始榜单记录与项目详情。</p>}
        {historical && board.dailyReview && <p>回顾日期：{board.dailyReview.date}（北京时间） · 本期 {board.projects.length} 项。优先避开最近 {board.dailyReview.lookbackDays} 个已发布回顾日；{board.dailyReview.relaxedRecentWindow ? '可选项目不足，已按最久未展示顺序补充。' : '本期无需放宽近期避重。'}当天发布后成员与顺序保持不变。</p>}
        <p>{historical ? '本期回顾发布' : '本次清单发布'}：{beijingTime(publishedAt)}{!historical && ` · 最近来源检查：${beijingTime(board.checkedAt)}`}</p>
        {!historical && board.refreshPolicy && <p>按来源周期日更，正常每日一次主更新、最多一次有条件补偿。当前应读取 Trendshift UTC 日期：{board.refreshPolicy.duePeriod.sourceDate}；源周期结束后等待 {board.refreshPolicy.readinessMinutes} 分钟（{board.refreshPolicy.timingBasis === 'provisional_safety_margin' ? '暂定安全余量，非来源更新承诺' : '当前配置'}）。GitHub 日榜保留其实际采集时间，不推定精确完整日窗口。</p>}
      </div></details>
    </>}
    {!historical && <RardarTodayOperations syncedAt={board?.publishedAt ?? null} checkedAt={board?.checkedAt ?? null} context="dual_board" />}
  </div>;
}
