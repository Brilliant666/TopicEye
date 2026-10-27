import RardarTrendingPage from '@/components/RardarTrendingPage';
import { loadPublishedBoard } from '@/lib/rardar-trending';
import { notFound } from 'next/navigation';
import { isRardarProduct } from '@/lib/product-profile';

export default async function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarTrendingPage board={await loadPublishedBoard('trending-today')} />;
}
