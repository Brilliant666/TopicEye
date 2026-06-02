'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import NotificationBell from '@/components/NotificationBell';
import { sourcesApi, contentsApi, favoritesApi } from '@/lib/api';

// App context - shared across pages
interface AppContextType {
  favorites: Set<number>;
  favoritePendingIds: Set<number>;
  topicCount: number;
  toggleFavorite: (id: number, options?: { throwOnError?: boolean }) => Promise<boolean>;
  refreshCounts: () => void;
}

const AppContext = createContext<AppContextType>({
  favorites: new Set(),
  favoritePendingIds: new Set(),
  topicCount: 0,
  toggleFavorite: async () => false,
  refreshCounts: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

const FAVORITES_STORAGE_KEY = 'topiceye_favorites';

function loadFavoritesFromStorage(): Set<number> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = localStorage.getItem(FAVORITES_STORAGE_KEY);
    if (!raw) return new Set();
    const arr: number[] = JSON.parse(raw);
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveFavoritesToStorage(favSet: Set<number>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify([...favSet]));
  } catch {}
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [favoritePendingIds, setFavoritePendingIds] = useState<Set<number>>(new Set());
  const favoritePendingRef = useRef<Set<number>>(new Set());
  const [contentCount, setContentCount] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);
  const [favoriteTotal, setFavoriteTotal] = useState(0);
  const [compactNav, setCompactNav] = useState(false);

  const refreshCounts = useCallback(async () => {
    try {
      const [contents, sources, allFavorites] = await Promise.all([
        contentsApi.list({ page_size: 1 }),
        sourcesApi.list(),
        favoritesApi.list({ page_size: 1 }),
      ]);
      setContentCount(contents.total || 0);
      setSourceCount(sources.total || sources.items?.length || 0);
      setFavoriteTotal(allFavorites.total || 0);

      // Also refresh favorites from backend
      const favs = await contentsApi.listFavorites({ page_size: 100 });
      const favIds = new Set((favs.items || []).map((item) => item.id));
      setFavorites(favIds);
    } catch {}
  }, []);

  useEffect(() => {
    setFavorites(loadFavoritesFromStorage());
    void refreshCounts();
  }, [refreshCounts]);

  useEffect(() => {
    const updateCompact = () => setCompactNav(window.innerWidth < 900);
    updateCompact();
    window.addEventListener('resize', updateCompact);
    return () => window.removeEventListener('resize', updateCompact);
  }, []);

  // Sync favorites to localStorage whenever it changes
  useEffect(() => {
    saveFavoritesToStorage(favorites);
  }, [favorites]);

  const toggleFavorite = useCallback(async (id: number, options?: { throwOnError?: boolean }): Promise<boolean> => {
    if (favoritePendingRef.current.has(id)) {
      return favorites.has(id);
    }
    const wasFavorited = favorites.has(id);
    favoritePendingRef.current.add(id);
    setFavoritePendingIds((prev) => new Set(prev).add(id));
    try {
      const result = await contentsApi.toggleFavorite(id);
      setFavorites((prev) => {
        const next = new Set(prev);
        if (result.is_favorited) {
          next.add(id);
        } else {
          next.delete(id);
        }
        return next;
      });
      if (result.is_favorited !== wasFavorited) {
        setFavoriteTotal((prev) => Math.max(0, prev + (result.is_favorited ? 1 : -1)));
      }
      return result.is_favorited;
    } catch (err) {
      console.error('Toggle favorite failed:', err);
      if (options?.throwOnError) {
        throw err;
      }
      return favorites.has(id);
    } finally {
      favoritePendingRef.current.delete(id);
      setFavoritePendingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, [favorites]);

  return (
    <AppContext.Provider value={{ favorites, favoritePendingIds, topicCount: contentCount, toggleFavorite, refreshCounts }}>
      <div className="flex h-dvh overflow-hidden">
        <Sidebar topicCount={contentCount} favCount={favoriteTotal} sourceCount={sourceCount} compact={compactNav} />
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-page">
          <div className="flex h-12 shrink-0 items-center justify-end border-b border-gray-100 bg-white px-6">
            <NotificationBell />
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {children}
          </div>
        </main>
      </div>
    </AppContext.Provider>
  );
}
