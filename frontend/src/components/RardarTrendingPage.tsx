'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ArrowRight, ArrowUpRight, BookOpen, Clock3, FolderGit2, ShieldCheck, Sparkles } from 'lucide-react';
import RardarTodayOperations from './RardarTodayOperations';
import RardarGrowthFacts from './RardarGrowthFacts';
import { narrativeSourceLabel, positioningSourceLabel } from '@/lib/rardar-intelligence';
import { boardTime, projectLink, safeSourceUrl, type TrendingBoard, type TrendingProject } from '@/lib/rardar-trending';
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
      {summary ? <p className={styles.officialTagline}>{summary}</p> : project.description ? <p className={styles.projectDescription}><small>原始介绍 · </small>{project.description}</p> : <p className={styles.projectDescription}>项目介绍暂未补齐，仓库和上榜记录仍可查看。</p>}
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
        {project.appearances.map(item => <p key={`${item.source}-${item.fetchedAt}`}>{boardSourceName[item.source]} #{item.rank} · {item.sourceDate ? `榜单日期 ${item.sourceDate}` : `采集于 ${boardTime(item.fetchedAt)}`} · {item.period} · {item.source === 'github' ? item.reportedDeltaPeriod : item.trendshiftMetricPeriod}</p>)}
          {project.totalStarsSource && <p>累计 Star 来源：{boardSourceName[project.totalStarsSource.source]} · 采集 {boardTime(project.totalStarsSource.fetchedAt)}</p>}
          {project.metadataSource && <p>语言、主题和许可证：GitHub 仓库元数据 · 读取 {boardTime(project.metadataSource.fetchedAt)}</p>}
        {historical && project.historicalEvidence?.map(item => <p key={item.sourceUrl}>来源报告历史上榜 {item.reportedAppearanceCount} 次；具体日期未知，不等于本地逐日记录。{safeSourceUrl(item.sourceUrl) && <a href={safeSourceUrl(item.sourceUrl)} target="_blank" rel="noopener noreferrer">核对来源 ↗</a>}</p>)}
        {historical && project.historicalRardarEvidence?.map(item => <p key={item.sourceGeneration}>Rardar #{item.rank} · {boardTime(item.windowStartedAt)} → {boardTime(item.windowEndedAt)} · 当时新增 {item.observedStarDelta.toLocaleString()} Star</p>)}
      </div></details>
      <div className={styles.cardActions}><Link className={styles.findPrefillLink} href={detailHref}>查看项目详情 <ArrowRight size={14} /></Link><a className={styles.githubLink} href={`https://github.com/${project.repository}`} target="_blank" rel="noopener noreferrer">GitHub <ArrowUpRight size={14} /></a></div>
    </div>
    <RardarGrowthFacts project={project} historical={historical} />
  </article>;
}

export function HistoricalContext({ project }: { project: TrendingProject }) {
  const context = project.historicalContext;
  if (!context) return <p className={styles.projectDescription}>历史日期未取得</p>;
  if (context.kind === 'reported_count') return <p className={styles.projectDescription}>来源报告曾上 GitHub 日榜 {context.reportedAppearanceCount} 次 · 具体日期未知，本地无对应逐日记录</p>;
  return <p className={styles.projectDescription}>{context.kind === 'rardar' ? 'Rardar 历史榜' : boardSourceName[context.source as keyof typeof boardSourceName]} #{context.rank} · {context.dateKind === 'capture' ? '采集于 ' : context.dateKind === 'window' ? '窗口结束 ' : '榜单日期 '}{boardTime(context.date)}</p>;
}

export default function RardarTrendingPage({ board, historical = false }: { board: TrendingBoard | null; historical?: boolean }) {
  const [visible, setVisible] = useState(20);
  return <div className={`${styles.page} ${styles.todayPage}`} data-rardar-route={historical ? '/historical-hot' : '/'}>
    <section className={`${styles.hero} ${styles.todayHero}`} data-testid="today-hero"><div className={styles.heroContent}>
      <p className={styles.eyebrow}>{historical ? 'History · Project Review' : 'Today · Trending Repositories'}</p>
      <h1 className={`${styles.heroTitle} ${styles.trendingHeroTitle}`}><span className={styles.trendingSectionName}>{historical ? '历史回顾' : '今日热榜'}</span><span className={styles.heroTitleAccent}>{historical ? '认识曾经错过的好项目' : <><span className={styles.heroPhrase}>看见热门项目，</span><span className={styles.heroPhrase}>读懂它的价值</span></>}</span></h1>
      <p className={styles.heroDescription}>{historical ? '从真实历史上榜记录认识项目，复用同一份项目档案与完整解读。历史关注与当前维护状态分别核对。' : 'GitHub Trending 与 Trendshift 自有日榜合并去重，保留两榜原始名次；项目解读帮助理解，不改变来源清单。'}</p>
      <div className={styles.foundationNotice}><span className={styles.noticePill}><ShieldCheck size={15} /> 真实来源 · 原始名次</span><span className={styles.noticePill}><Sparkles size={15} /> 共享项目档案 · 按需深度解读</span></div>
    </div></section>
    <div className={styles.sectionHeading}><div><h2>{historical ? '历史项目回顾' : '双榜项目清单'}</h2><p>{historical ? '已有解读优先，再按累计 Star 浏览；历史表现不代表今日增长。' : '按来源报告的 Star 增长降序排列；双榜项目优先采用 GitHub Trending。'}</p></div>{board?.publishedAt && <span className={styles.timestamp}>清单发布 {boardTime(board.publishedAt)}</span>}</div>
    {!historical && board && <p className={styles.boardSourceSummary} aria-label="两源读取状态">{board.sources.map(source => <span key={source.source}>{source.label}：{source.status === 'healthy' ? '读取成功' : source.status === 'stale' ? '历史缓存' : '读取失败'} · 源榜 {boardTime(source.sourceDate)} · 采集 {boardTime(source.fetchedAt)}</span>)}</p>}
    {!board ? <section className={styles.emptyExactCard} role="status"><Clock3 size={28} /><div><h3>已保存清单暂时不可用</h3><p>请稍后重试；普通阅读不会触发采集或模型请求。</p></div></section> : <>
      <section className={styles.rankingList} aria-label={historical ? '历史回顾项目' : '双榜今日热榜'}>{board.projects.slice(0, visible).map((project, index) => <TrendingCard key={project.projectId} project={project} generationId={board.generationId} historical={historical} index={index} />)}</section>
      {board.projects.length === 0 && <section className={styles.emptyExactCard}><BookOpen size={28} /><p>尚无已保存的{historical ? '历史上榜记录' : '有效榜单'}。</p></section>}
      {visible < board.projects.length && <div className={styles.expandBoard}><button type="button" className={styles.boardLoadMore} onClick={() => setVisible(value => value + 20)}>加载更多（剩余 {board.projects.length - visible} 项）</button></div>}
      <details className={styles.provenanceDetails}><summary><BookOpen size={16} /> 来源与更新时间 <span>{board.projects.length} 个去重项目</span></summary><div className={styles.provenanceDetailsBody}>
        {!historical && board.sources.map(source => <p key={source.source}><strong>{source.label}</strong> · {source.count} 项 · 榜单日期 {boardTime(source.sourceDate)} · {source.status === 'healthy' ? '读取成功' : source.status === 'stale' ? '显示历史缓存，来源尚未更新' : '来源暂不可用'} · 采集 {boardTime(source.fetchedAt)}</p>)}
        <p>本次清单发布：{boardTime(board.publishedAt)}{!historical && ` · 最近来源检查：${boardTime(board.checkedAt)}`}</p>
      </div></details>
    </>}
    {!historical && <RardarTodayOperations syncedAt={board?.publishedAt ?? null} checkedAt={board?.checkedAt ?? null} context="dual_board" />}
  </div>;
}
