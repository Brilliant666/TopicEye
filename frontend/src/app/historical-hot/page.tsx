import { notFound } from 'next/navigation';
import RardarTrendingPage from '@/components/RardarTrendingPage';
import { isRardarProduct } from '@/lib/product-profile';
import { loadPublishedBoard } from '@/lib/rardar-trending';

export default async function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarTrendingPage historical board={await loadPublishedBoard('historical-hot')} />;
}
