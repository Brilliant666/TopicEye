import { notFound } from 'next/navigation';

import RardarFindProjectPage from '@/components/RardarFindProjectPage';
import { isRardarProduct } from '@/lib/product-profile';

export default function Page() {
  if (!isRardarProduct()) notFound();
  return <RardarFindProjectPage />;
}
