import { notFound } from 'next/navigation';

import RardarFindProjectPage from '@/components/RardarFindProjectPage';
import { isRardarProduct } from '@/lib/product-profile';
import { parsePublicGitHubRepositoryUrl } from '@/lib/rardar-repository-url';

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ repositoryUrl?: string | string[]; runId?: string | string[] }>;
}) {
  if (!isRardarProduct()) notFound();
  const params = await searchParams;
  const raw = params.repositoryUrl;
  const single = typeof raw === 'string' ? raw : null;
  const parsed = single ? parsePublicGitHubRepositoryUrl(single) : null;
  return (
    <RardarFindProjectPage
      initialRunId={typeof params.runId === 'string' ? params.runId : ''}
      initialRepositoryUrl={parsed?.url || ''}
      importedRepository={parsed?.repository || null}
      invalidPrefill={single !== null && parsed === null}
    />
  );
}
