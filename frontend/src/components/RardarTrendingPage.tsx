'use client';

import Link from 'next/link';
import { useState } from 'react';
import RardarTodayOperations from './RardarTodayOperations';
import { boardTime, projectLink, safeSourceUrl, type TrendingBoard, type TrendingProject } from '@/lib/rardar-trending';

const sourceName = { github: 'GitHub Trending', trendshift: 'Trendshift' };

export function TrendingCard({ project, generationId, historical = false }: { project: TrendingProject; generationId: string; historical?: boolean }) {
  return <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7" data-project-id={project.projectId}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h2 className="min-w-0 break-words text-xl font-bold text-slate-900"><Link href={projectLink(project.projectId, generationId, historical)}>{project.repository}</Link></h2>
      {project.totalStars !== null && <span className="text-sm text-slate-600">★ {project.totalStars.toLocaleString()} 累计</span>}
    </div>
    {project.dualListed && !historical && <span className="mt-3 inline-block rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-blue-700">双榜上榜</span>}
    <p className="mt-4 leading-7 text-slate-700">{project.profile?.summary || project.description || '项目资料暂未补齐，可先查看原仓库。'}</p>
    {!project.profile && project.description && <p className="mt-1 text-xs text-slate-500">原始介绍</p>}
    {project.profile?.positioning && project.profile.positioning !== project.profile.summary && <p className="mt-2 leading-7 text-slate-600">{project.profile.positioning}</p>}
    <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-600">
      {project.appearances.map((appearance) => <span key={`${appearance.source}-${appearance.sourceDate}`} className="rounded-lg bg-slate-50 px-3 py-2">
        {sourceName[appearance.source]} #{appearance.rank} · {boardTime(appearance.sourceDate)}
        {appearance.reportedDelta !== null && <span> · 来源报告周期增长 +{appearance.reportedDelta.toLocaleString()}</span>}
      </span>)}
    </div>
    {historical && <p className="mt-3 text-sm text-slate-500">本地保存 {project.historyAppearances ?? project.appearances.length} 次榜单记录 · 最早采集 {boardTime(project.firstSeenAt)}</p>}
    {historical && project.historicalEvidence?.map(evidence => <p className="mt-2 text-sm text-slate-600" key={evidence.sourceUrl}>GitHub 历史上榜 {evidence.reportedAppearanceCount} 次（来源报告，具体日期未知）{safeSourceUrl(evidence.sourceUrl) && <a href={safeSourceUrl(evidence.sourceUrl)} className="ml-2 text-blue-700" target="_blank" rel="noopener noreferrer">核对历史来源 ↗</a>}</p>)}
    <div className="mt-5 flex flex-wrap gap-4 text-sm font-medium">
      <Link className="text-blue-700" href={projectLink(project.projectId, generationId, historical)}>了解项目 →</Link>
      <a className="text-slate-600" href={`https://github.com/${project.repository}`} target="_blank" rel="noopener noreferrer">原仓库 ↗</a>
    </div>
  </article>;
}

export default function RardarTrendingPage({ board, historical = false }: { board: TrendingBoard | null; historical?: boolean }) {
  const [visible, setVisible] = useState(20);
  return <div className="mx-auto max-w-6xl px-4 pt-8 pb-28 sm:px-6">
    <header className="mb-7"><p className="text-sm font-semibold text-blue-700">{historical ? '认识曾经错过的项目' : '两个来源，一份项目清单'}</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{historical ? '历史热门' : '今日热榜'}</h1>
      <p className="mt-4 max-w-3xl leading-7 text-slate-600">{historical ? '从有记录的历史榜单中认识项目。历史关注不等于当前维护承诺，解读以已取得的资料为依据。' : '合并 GitHub Trending 全语言日榜与 Trendshift 自有日榜，按来源原始顺序交错展示。这里不是全 GitHub 精确增长排名。'}</p>
    </header>
    {!historical && <RardarTodayOperations syncedAt={board?.publishedAt ?? null} />}
    {!board ? <p role="status" className="rounded-xl bg-slate-50 p-5">暂时无法读取已保存榜单，请稍后重试。没有触发采集或模型请求。</p> : <>
      {!historical && <div className="my-5 flex flex-wrap gap-3 text-sm">{board.sources.map(source => <div key={source.source} className="rounded-xl border border-slate-200 bg-white p-3">
        <strong>{source.label}</strong> · {source.count} 项 · {boardTime(source.sourceDate)}
        <p className="mt-1 text-xs text-slate-500">{source.status === 'healthy' ? '本次读取成功' : source.status === 'stale' ? '显示历史缓存，来源尚未更新' : '来源暂不可用'} · 采集 {boardTime(source.fetchedAt)}</p>
      </div>)}</div>}
      <p className="my-5 text-sm text-slate-500">{board.projects.length} 个去重项目 · 保存于 {boardTime(board.publishedAt)}{!historical && ` · 最近检查 ${boardTime(board.checkedAt)}`}</p>
      <div className="grid gap-4">{board.projects.slice(0, visible).map(project => <TrendingCard key={project.projectId} project={project} generationId={board.generationId} historical={historical} />)}</div>
      {board.projects.length === 0 && <p className="rounded-xl bg-slate-50 p-5">尚无已保存的{historical ? '历史上榜记录' : '有效榜单'}。</p>}
      {visible < board.projects.length && <button className="mx-auto mt-6 block rounded-xl border border-blue-200 bg-white px-6 py-3 text-blue-700" onClick={() => setVisible(value => value + 20)}>加载更多（剩余 {board.projects.length - visible} 项）</button>}
    </>}
  </div>;
}
