import { notFound } from 'next/navigation';

import RardarPausedPage from '@/components/RardarPausedPage';
import { isRardarProduct } from '@/lib/product-profile';

export default function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarPausedPage title="热点资讯" />;
}
