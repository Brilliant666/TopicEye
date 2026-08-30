import { notFound } from 'next/navigation';

import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { isRardarProduct } from '@/lib/product-profile';
import { loadDiscoverProjectDetail } from '@/lib/rardar-discover';
import { loadProjectDetail } from '@/lib/rardar-intelligence';

export default async function ProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ githubRepositoryId: string }>;
  searchParams: Promise<{ generation?: string | string[]; discoverGeneration?: string | string[] }>;
}) {
  if (!isRardarProduct()) notFound();
  const { githubRepositoryId: rawIdentifier } = await params;
  const query = await searchParams;
  const generation = typeof query.generation === 'string' ? query.generation : null;
  const discoverGeneration = typeof query.discoverGeneration === 'string' ? query.discoverGeneration : null;
  if (
    !/^[1-9]\d{0,19}$/.test(rawIdentifier)
    || (generation === null) === (discoverGeneration === null)
    || (generation?.length || discoverGeneration?.length || 0) > 127
  ) notFound();
  const identifier = Number(rawIdentifier);
  if (!Number.isSafeInteger(identifier)) notFound();
  const result = discoverGeneration
    ? await loadDiscoverProjectDetail(identifier, discoverGeneration)
    : await loadProjectDetail(identifier, generation || '');
  if (result.kind === 'not_found') notFound();
  if (result.kind === 'revision_mismatch') {
    return <ProjectError title="这个项目快照已不匹配" detail={`请回到${discoverGeneration ? '发现页' : '今日榜单'}，从当前 generation 重新进入详情。`} />;
  }
  if (result.kind === 'error') {
    return <ProjectError title="项目详情暂时不可用" detail={`Serving Projection 已安全停止读取 · ${result.code}`} />;
  }
  return <RardarProjectDetailPage detail={result.detail} />;
}

function ProjectError({ title, detail }: { title: string; detail: string }) {
  return <main style={{ maxWidth: 900, margin: '0 auto', padding: '4rem 1.5rem' }}><h1>{title}</h1><p>{detail}</p></main>;
}
