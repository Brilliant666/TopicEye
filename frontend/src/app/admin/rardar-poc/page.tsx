'use client';

import { useEffect, useState } from 'react';
import { Activity, Database, FlaskConical, ShieldCheck } from 'lucide-react';
import { rardarRequest } from '@/lib/rardar-api';

type Diagnostics = { productProfile: string; artifactRevision: string; candidateFixtureRevision: string; provider: { name: string; mode: string; model: string; networkCalls: boolean }; jobs: Record<string, number>; aiCalls: { total: number; failed: number; cacheHits: number }; circuit: { state: string; failure_count: number }; featureFlags: Record<string, unknown> };

export default function RardarPocAdminPage() {
  const [data, setData] = useState<Diagnostics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void rardarRequest<Diagnostics>('/admin/diagnostics').then(setData).catch((reason) => setError(String(reason))); }, []);
  return <div className="mx-auto max-w-6xl p-6 lg:p-10"><div className="mb-7"><p className="text-xs font-black uppercase tracking-[0.18em] text-blue-600">TopicEye admin · Rardar adapter</p><h1 className="mt-2 text-3xl font-black">Rardar POC 诊断</h1></div>{error && <p className="rounded-xl bg-red-50 p-4 text-sm font-bold text-red-700">{error}</p>}{!data ? <p className="text-sm text-slate-500">读取控制面诊断…</p> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><Card icon={<ShieldCheck />} label="Product profile" value={data.productProfile} detail={data.artifactRevision} /><Card icon={<FlaskConical />} label="Mock provider" value={`${data.provider.name} / ${data.provider.model}`} detail={`network=${data.provider.networkCalls}`} /><Card icon={<Database />} label="Durable jobs" value={String(Object.values(data.jobs).reduce((a, b) => a + b, 0))} detail={JSON.stringify(data.jobs)} /><Card icon={<Activity />} label="AI calls / circuit" value={`${data.aiCalls.total} / ${data.circuit.state}`} detail={`failed=${data.aiCalls.failed} cache=${data.aiCalls.cacheHits}`} /></div>}</div>;
}

function Card({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) { return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><span className="text-blue-600">{icon}</span><p className="mt-5 text-xs font-bold uppercase tracking-wider text-slate-400">{label}</p><p className="mt-1 break-words font-black text-slate-900">{value}</p><p className="mt-3 break-all font-mono text-[10px] leading-5 text-slate-400">{detail}</p></article>; }
