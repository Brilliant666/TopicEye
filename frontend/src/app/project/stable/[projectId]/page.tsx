import { notFound } from 'next/navigation';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import { isRardarProduct } from '@/lib/product-profile';
import { loadTrending, type TrendingDetail } from '@/lib/rardar-trending';

export default async function Page({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  if (!isRardarProduct()) notFound();
  const { projectId } = await params;
  const query = await searchParams;
  if (!/^[a-z0-9][a-z0-9-]{10,100}$/.test(projectId)) notFound();
  const historical = query.history === '1';
  const generation = typeof query.generation === 'string' ? query.generation : '';
  if (!historical && !/^boards-[a-f0-9]{64}$/.test(generation)) notFound();
  const detail = await loadTrending<TrendingDetail>(historical ? `historical-projects/${encodeURIComponent(projectId)}` : `trending-projects/${encodeURIComponent(projectId)}?generation=${encodeURIComponent(generation)}`);
  if (!detail || detail.projectId !== projectId) notFound();
  return <RardarProjectDetailPage detail={detail} historical={historical} />;
}
