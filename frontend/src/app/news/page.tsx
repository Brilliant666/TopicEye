import { notFound } from 'next/navigation';

import RardarHotspotNewsPage from '@/components/RardarHotspotNewsPage';
import { loadHotspotNews } from '@/lib/rardar-hotspot-news';
import { isRardarProduct } from '@/lib/product-profile';

type NewsSearchParams = Promise<Record<string, string | string[] | undefined>>;

function scalar(value: string | string[] | undefined): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

export default async function Page({ searchParams }: { searchParams: NewsSearchParams }) {
  if (!isRardarProduct()) notFound();
  const params = await searchParams;
  const sort = scalar(params.sort) === 'latest' ? 'latest' : 'balanced';
  const parsedPage = Number.parseInt(scalar(params.page) || '1', 10);
  return (
    <RardarHotspotNewsPage
      result={await loadHotspotNews(fetch, undefined, {
        source: scalar(params.source),
        topic: scalar(params.topic),
        sort,
        page: Number.isSafeInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1,
      })}
    />
  );
}
