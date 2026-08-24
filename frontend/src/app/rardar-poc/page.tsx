import Link from 'next/link';
import { ArrowUpRight, Clock3, Code2, ShieldCheck, Sparkles, Telescope } from 'lucide-react';
import { fetchExplosionBoard } from '@/lib/rardar-api';

const number = new Intl.NumberFormat('zh-CN');

export default async function RardarExplosionPage() {
  let board;
  try {
    board = await fetchExplosionBoard();
  } catch {
    return (
      <section className="mx-auto max-w-4xl px-4 py-20 text-center sm:px-7">
        <div className="rounded-3xl border border-red-200 bg-white p-10 shadow-sm">
          <p className="text-sm font-black uppercase tracking-[0.2em] text-red-500">Fail closed</p>
          <h1 className="mt-3 text-3xl font-black">已验证的爆发榜 artifact 暂时不可读</h1>
          <p className="mt-3 text-slate-500">页面不会回退到数据库评分或拼接不同 revision 的事实。</p>
        </div>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-7 lg:px-10 lg:py-12" data-artifact-revision={board.artifactRevision}>
      <section className="relative overflow-hidden rounded-[32px] border border-blue-100 bg-white px-6 py-8 shadow-[0_24px_80px_rgba(37,99,235,0.08)] sm:px-10 lg:px-14 lg:py-12">
        <div className="absolute -right-24 -top-32 h-80 w-80 rounded-full bg-blue-100/70 blur-3xl" />
        <div className="absolute right-20 top-16 h-24 w-24 rounded-full bg-cyan-100 blur-2xl" />
        <div className="relative grid gap-8 lg:grid-cols-[1fr_360px] lg:items-end">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-black text-blue-700">
              <Sparkles size={14} /> 基于多源召回与连续观察的 POC 事实榜
            </div>
            <h1 className="max-w-4xl text-4xl font-black leading-[1.06] tracking-[-0.04em] text-slate-950 sm:text-5xl lg:text-6xl">
              过去 24 小时，哪些项目正在<span className="text-blue-600">快速爆发？</span>
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-7 text-slate-500 sm:text-lg">
              精确名次只由自有 observation fixture 的 Star 增量决定。AI 仅解释，不排序、不补位。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Metric label="精确主榜" value="Top 5" />
            <Metric label="待验证新入榜" value={`${board.firstSeenPending.length} 个`} />
            <Metric label="召回候选" value={number.format(board.coverage.recalledCandidates)} />
            <Metric label="Artifact" value={board.artifactRevision.replace('explosion-poc-', '')} mono />
          </div>
        </div>
      </section>

      <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section aria-labelledby="exact-board-title">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-blue-600">Exact 24h delta</p>
              <h2 id="exact-board-title" className="mt-1 text-2xl font-black tracking-tight">今日爆发榜</h2>
            </div>
            <span className="text-xs font-semibold text-slate-400">{new Date(board.publishedAt).toLocaleString('zh-CN')}</span>
          </div>
          <div className="space-y-3">
            {board.exactTop.map((project) => (
              <article key={project.projectId} data-testid="explosion-project" className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg hover:shadow-blue-900/5 sm:p-6">
                <div className="grid gap-5 sm:grid-cols-[64px_1fr_auto] sm:items-start">
                  <div className={`grid h-14 w-14 place-items-center rounded-2xl text-2xl font-black ${project.rank === 1 ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25' : 'bg-blue-50 text-blue-700'}`}>
                    {String(project.rank).padStart(2, '0')}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <a href={`https://github.com/${project.repository}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-lg font-black tracking-tight hover:text-blue-600 sm:text-xl">
                        <Code2 size={18} /> {project.repository} <ArrowUpRight size={15} />
                      </a>
                      <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-black text-emerald-700">+{number.format(project.observedStarDelta)} Star / 24h</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{project.summaryZh}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {(project.ai.profile?.coreCapabilities || project.coreCapabilities || []).map((capability) => <span key={capability} className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{capability}</span>)}
                    </div>
                    <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-xs leading-5 text-slate-600">
                      <span className="font-black text-blue-700">AI 爆发原因判断 · </span>
                      {project.ai.profile?.whyTrendingHypothesis || project.ai.label}
                    </div>
                  </div>
                  <div className="flex gap-5 text-right sm:block">
                    <div><p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Star</p><p className="mt-1 text-lg font-black">{number.format(project.totalStars)}</p></div>
                    <div className="sm:mt-4"><p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Forks</p><p className="mt-1 text-sm font-bold text-slate-600">{number.format(project.forks)}</p></div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-cyan-200 bg-gradient-to-br from-cyan-50 to-white p-5">
            <div className="flex items-center gap-2 text-cyan-800"><Telescope size={18} /><h2 className="font-black">新入榜待验证</h2></div>
            <p className="mt-2 text-xs leading-5 text-slate-500">首次发现立即展示；观察满 24 小时前绝不进入精确榜。</p>
            <div className="mt-4 space-y-3">
              {board.firstSeenPending.map((project) => (
                <article key={project.projectId} data-testid="first-seen-project" className="rounded-xl border border-cyan-100 bg-white p-3.5">
                  <p className="font-black text-slate-800">{project.repository}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{project.summaryZh}</p>
                  <div className="mt-2 flex items-center justify-between text-[11px] font-bold text-cyan-700"><span>{project.observedWindowHours}h +{project.observedWindowStarDelta}</span><span>{number.format(project.totalStars)} Star</span></div>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2"><ShieldCheck size={18} className="text-blue-600" /><h2 className="font-black">覆盖与证据</h2></div>
            <p className="mt-3 text-sm leading-6 text-slate-500">{board.coverage.statement}</p>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <Coverage label="成功查询" value={board.coverage.successfulQueries} />
              <Coverage label="持续观察" value={board.coverage.observedRepositories} />
            </dl>
            <p className="mt-4 flex items-center gap-1.5 text-[11px] font-semibold text-slate-400"><Clock3 size={13} /> 一次响应只绑定 {board.artifactRevision}</p>
          </section>

          <Link href="/find-project" className="block rounded-2xl bg-blue-600 p-5 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-blue-100">Next action</p>
            <h2 className="mt-2 text-xl font-black">告诉我你要做什么</h2>
            <p className="mt-2 text-sm leading-6 text-blue-100">用 RequirementProfile 从真实候选 fixture 找 3 个可复用方案。</p>
          </Link>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4"><p className="text-[10px] font-black uppercase tracking-wider text-blue-500">{label}</p><p className={`mt-1 text-lg font-black text-slate-900 ${mono ? 'font-mono text-sm' : ''}`}>{value}</p></div>;
}

function Coverage({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-slate-50 p-3"><dt className="text-slate-400">{label}</dt><dd className="mt-1 text-lg font-black text-slate-800">{number.format(value)}</dd></div>;
}
