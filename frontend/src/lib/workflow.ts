import { favoritesApi } from '@/lib/api';
import type { FavoriteStatus } from '@/types';

type StartContentWorkflowOptions = {
  contentId: number;
  title: string;
  isFavorited: boolean;
  toggleFavorite: (id: number, options?: { throwOnError?: boolean }) => Promise<boolean>;
  router: { push: (href: string) => void };
  status?: FavoriteStatus;
};

export async function startContentWorkflow({
  contentId,
  title,
  isFavorited,
  toggleFavorite,
  router,
  status = 'researching',
}: StartContentWorkflowOptions): Promise<void> {
  let favorited = isFavorited;
  if (!favorited) {
    favorited = await toggleFavorite(contentId, { throwOnError: true });
  }
  if (!favorited) {
    throw new Error('素材未加入收藏夹，请重试');
  }

  const state = await favoritesApi.state({ target_type: 'content', target_ids: [contentId] });
  const favoriteId = state.items.find((item) => item.is_favorited)?.favorite_id;
  if (!favoriteId) {
    throw new Error('收藏记录未同步，请刷新后重试');
  }

  await favoritesApi.update(favoriteId, { status });

  const params = new URLSearchParams({
    target_type: 'content',
    status,
    keyword: title,
  });
  router.push(`/favorites?${params.toString()}`);
}
