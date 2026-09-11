import Link from 'next/link';
import { notFound } from 'next/navigation';
import { isRardarProduct } from '@/lib/product-profile';
import { boardTime, loadTrending, safeSourceUrl, type TrendingDetail } from '@/lib/rardar-trending';

export default async function Page({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  if (!isRardarProduct()) notFound();
  const { projectId } = await params;
  const query = await searchParams;
  if (!/^[a-z0-9][a-z0-9-]{10,100}$/.test(projectId)) notFound();
  const historical = query.history === '1';
  const generation = typeof query.generation === 'string' ? query.generation : '';
  if (!historical && !/^boards-[a-f0-9]{64}$/.test(generation)) notFound();
  const project = await loadTrending<TrendingDetail>(historical ? `historical-projects/${encodeURIComponent(projectId)}` : `trending-projects/${encodeURIComponent(projectId)}?generation=${encodeURIComponent(generation)}`);
  if (!project || project.projectId !== projectId) notFound();
  const profile = project.profile;
  return <article className="mx-auto max-w-4xl px-5 pt-8 pb-28">
    <Link className="text-sm text-blue-700" href={historical ? '/historical-hot' : '/'}>← {historical ? '历史热门' : '今日热榜'}</Link>
    <h1 className="mt-6 break-words text-3xl font-bold">{project.repository}</h1>
    <p className="mt-4 text-lg leading-8 text-slate-700">{profile?.summary || project.description || '资料暂未补齐，仓库身份和上榜记录可查。'}</p>
    <p className="mt-2 text-sm text-slate-500">{profile ? `${profile.sourceLabel || '已保存的项目解读'} · ${boardTime(profile.generatedAt)}` : project.description ? '原始介绍，尚无中文解读' : '暂无可靠介绍'}</p>
    <div className="my-5 flex flex-wrap gap-4 text-sm"><a href={`https://github.com/${project.repository}`} target="_blank" rel="noopener noreferrer" className="text-blue-700">访问 GitHub ↗</a><Link href={`/find?repositoryUrl=${encodeURIComponent(`https://github.com/${project.repository}`)}`} className="text-blue-700">结合我的需求找项目 →</Link></div>
    <section className="my-6 rounded-xl bg-slate-50 p-5"><h2 className="font-bold">上榜依据</h2>{project.totalStars !== null && <p className="mt-2">累计 Star：{project.totalStars.toLocaleString()}</p>}{project.appearances.map(a => <p key={`${a.source}-${a.sourceDate}`} className="mt-2">{a.source === 'github' ? 'GitHub Trending' : 'Trendshift'} 日榜 #{a.rank} · {boardTime(a.sourceDate)}{a.reportedDelta !== null ? ` · 来源报告周期增长 +${a.reportedDelta}` : ''} <span className="text-sm text-slate-500">（采集 {boardTime(a.fetchedAt)}）</span></p>)}</section>
    {project.historicalEvidence?.map(evidence => <p className="my-4 text-sm text-slate-600" key={evidence.sourceUrl}>GitHub 历史上榜 {evidence.reportedAppearanceCount} 次（来源报告，具体日期未知）。采集于 {boardTime(evidence.fetchedAt)}。{safeSourceUrl(evidence.sourceUrl) && <a href={safeSourceUrl(evidence.sourceUrl)} className="text-blue-700" target="_blank" rel="noopener noreferrer"> 核对历史来源 ↗</a>}</p>)}
    {profile?.positioning && <section className="my-7"><h2 className="text-xl font-bold">项目定位</h2><p className="mt-3 leading-7">{profile.positioning}</p></section>}
    {[["主要能力", profile?.capabilities], ["典型用途", profile?.useCases], ["限制与待确认", profile?.limitations]].map(([title, items]) => Array.isArray(items) && items.length > 0 && <section className="my-7" key={String(title)}><h2 className="text-xl font-bold">{String(title)}</h2><ul className="mt-3 list-disc space-y-2 pl-5 leading-7">{items.map(item => <li key={item}>{item}</li>)}</ul></section>)}
    {profile?.startHere?.length ? <section className="my-7"><h2 className="text-xl font-bold">继续核对与使用</h2><ul className="mt-3 space-y-2">{profile.startHere.map(item => safeSourceUrl(item.url) && <li key={item.url}><a className="text-blue-700" href={safeSourceUrl(item.url)} target="_blank" rel="noopener noreferrer">{item.label} ↗</a></li>)}</ul></section> : null}
    {profile && <p className="mt-7 text-sm text-slate-500">解读依据已读取资料，不代表已安装或运行验证。{safeSourceUrl(profile.sourceUrl) && <a href={safeSourceUrl(profile.sourceUrl)} className="text-blue-700"> 查看资料来源</a>}</p>}
    {project.materialState !== 'complete' && <p className="mt-6 text-sm text-slate-500">部分项目资料尚未补齐，不影响查看上榜事实和原仓库。</p>}
  </article>;
}
