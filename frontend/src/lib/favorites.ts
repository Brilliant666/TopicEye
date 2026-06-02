import type { FavoriteItem, FavoriteTargetType } from '@/types';

export interface FavoriteTargetRef {
  target_type: FavoriteTargetType;
  target_id?: number | null;
  target_key?: string | null;
}

export interface FavoriteCreatePayload extends FavoriteTargetRef {
  title?: string;
  url?: string | null;
  cover_url?: string | null;
  source_name?: string | null;
  collection_id?: number | null;
  tags?: unknown;
  note?: string | null;
  status?: FavoriteItem['status'];
  snapshot?: Record<string, unknown> | null;
}

export interface FavoriteTargetState {
  target_key: string;
  is_favorited: boolean;
  favorite_id: number | null;
}

export function getFavoriteTargetKey(target: FavoriteTargetRef): string {
  const targetKey = typeof target.target_key === 'string' ? target.target_key.trim() : '';
  if (targetKey) return `${target.target_type}:${targetKey}`;
  if (target.target_id !== undefined && target.target_id !== null) {
    return `${target.target_type}:${target.target_id}`;
  }
  throw new Error('target_id or target_key is required');
}

export function getContentFavoriteKey(id: number): string {
  return getFavoriteTargetKey({ target_type: 'content', target_id: id });
}

export function favoriteItemToTargetKey(item: FavoriteItem): string {
  return getFavoriteTargetKey({
    target_type: item.target_type,
    target_id: item.target_id,
    target_key: item.target_key,
  });
}
