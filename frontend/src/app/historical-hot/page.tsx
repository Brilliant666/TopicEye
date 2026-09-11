import { notFound } from 'next/navigation';
import RardarTrendingPage from '@/components/RardarTrendingPage';
import { isRardarProduct } from '@/lib/product-profile';
import { loadTrending, type TrendingBoard } from '@/lib/rardar-trending';

export default async function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarTrendingPage historical board={await loadTrending<TrendingBoard>('historical-hot')} />;
}
