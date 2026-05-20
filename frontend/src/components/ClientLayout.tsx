'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { sourcesApi, contentsApi } from '@/lib/api';

// App context - shared across pages
interface AppContextType {
  favorites: Set<number>;
  topicCount: number;
  toggleFavorite: (id: number) => void;
  refreshCounts: () => void;
}

const AppContext = createContext<AppContextType>({
  favorites: new Set(),
  topicCount: 0,
  toggleFavorite: () => {},
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
  const [favorites, setFavorites] = useState<Set<number>>(() => loadFavoritesFromStorage());
  const [contentCount, setContentCount] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);

  const refreshCounts = useCallback(async () => {
    try {
      const [contents, sources] = await Promise.all([
        contentsApi.list({ page_size: 1 }),
        sourcesApi.list(),
      ]);
      setContentCount(contents.total || 0);
      setSourceCount(sources.total || sources.items?.length || 0);

      // Also refresh favorites from backend
      const favs = await contentsApi.listFavorites({ page_size: 100 });
      const favIds = new Set((favs.items || []).map((item: any) => item.id));
      setFavorites(favIds);
    } catch {}
  }, []);

  useEffect(() => {
    refreshCounts();
  }, [refreshCounts]);

  // Sync favorites to localStorage whenever it changes
  useEffect(() => {
    saveFavoritesToStorage(favorites);
  }, [favorites]);

  const toggleFavorite = useCallback(async (id: number) => {
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
    } catch (err) {
      console.error('Toggle favorite failed:', err);
    }
  }, []);

  return (
    <AppContext.Provider value={{ favorites, topicCount: contentCount, toggleFavorite, refreshCounts }}>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        <Sidebar topicCount={contentCount} favCount={favorites.size} sourceCount={sourceCount} />
        <main style={{ flex: 1, overflow: 'hidden', background: '#F7F7F8' }}>
          {children}
        </main>
      </div>
    </AppContext.Provider>
  );
}
