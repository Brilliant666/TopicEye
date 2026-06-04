'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { favoritesApi } from '@/lib/api';
import { useAppContext } from '@/components/ClientLayout';

function normalizeIds(ids: Array<number | null | undefined>): number[] {
  return Array.from(new Set(
    ids
      .filter((id): id is number => typeof id === 'number' && Number.isFinite(id))
      .sort((a, b) => a - b)
  ));
}

export function useContentFavoriteStates(ids: Array<number | null | undefined>) {
  const { currentUser, favorites } = useAppContext();
  const [serverFavoriteIds, setServerFavoriteIds] = useState<Set<number>>(new Set());
  const [validatedKey, setValidatedKey] = useState('');
  const [refreshVersion, setRefreshVersion] = useState(0);
  const requestSeq = useRef(0);

  const idsKey = useMemo(() => normalizeIds(ids).join(','), [ids]);
  const normalizedIds = useMemo(() => (
    idsKey ? idsKey.split(',').map((id) => Number(id)).filter((id) => Number.isFinite(id)) : []
  ), [idsKey]);

  const refresh = useCallback(() => {
    setRefreshVersion((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!idsKey || !currentUser) {
      setServerFavoriteIds(new Set());
      setValidatedKey('');
      return;
    }

    const seq = requestSeq.current + 1;
    requestSeq.current = seq;

    (async () => {
      try {
        const targetIds = idsKey.split(',').map((id) => Number(id)).filter((id) => Number.isFinite(id));
        const state = await favoritesApi.state({
          target_type: 'content',
          target_ids: targetIds,
        });
        if (requestSeq.current !== seq) return;
        const next = new Set<number>();
        for (const item of state.items || []) {
          if (!item.is_favorited) continue;
          const id = Number(item.target_key);
          if (Number.isFinite(id)) next.add(id);
        }
        setServerFavoriteIds(next);
        setValidatedKey(idsKey);
      } catch {
        if (requestSeq.current !== seq) return;
        setValidatedKey('');
      }
    })();
  }, [currentUser, idsKey, refreshVersion]);

  const favoriteIds = useMemo(() => {
    if (!idsKey || validatedKey !== idsKey) {
      return new Set(normalizedIds.filter((id) => favorites.has(id)));
    }
    return serverFavoriteIds;
  }, [favorites, idsKey, normalizedIds, serverFavoriteIds, validatedKey]);

  const isFavorited = useCallback((id: number) => favoriteIds.has(id), [favoriteIds]);

  return { favoriteIds, isFavorited, refresh };
}
