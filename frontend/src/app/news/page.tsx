import { notFound } from 'next/navigation';

import RardarHotspotNewsPage from '@/components/RardarHotspotNewsPage';
import { loadHotspotNews } from '@/lib/rardar-hotspot-news';
import { isRardarProduct } from '@/lib/product-profile';

export default async function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarHotspotNewsPage result={await loadHotspotNews()} />;
}
