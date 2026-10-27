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
  const readingRevision = query.readingRevision;
  if (readingRevision !== undefined && (typeof readingRevision !== 'string' || !/^[a-f0-9]{64}$/.test(readingRevision))) notFound();
  if (!historical && !/^boards-[a-f0-9]{64}$/.test(generation)) notFound();
  const parameters = new URLSearchParams();
  if (!historical) parameters.set('generation', generation);
  if (readingRevision) parameters.set('readingRevision', readingRevision);
  const queryString = parameters.toString();
  const detail = await loadTrending<TrendingDetail>(`${historical ? 'historical-projects' : 'trending-projects'}/${encodeURIComponent(projectId)}${queryString ? `?${queryString}` : ''}`);
  if (!detail || detail.projectId !== projectId || (readingRevision && detail.readingRevision !== readingRevision)) notFound();
  return <RardarProjectDetailPage detail={detail} historical={historical} />;
}
