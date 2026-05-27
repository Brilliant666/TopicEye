'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import NotificationBell from '@/components/NotificationBell';
import { T } from '@/lib/design-tokens';
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
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [contentCount, setContentCount] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);
  const [compactNav, setCompactNav] = useState(false);

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
      <div style={{ display: 'flex', height: '100dvh', overflow: 'hidden' }}>
        <Sidebar topicCount={contentCount} favCount={favorites.size} sourceCount={sourceCount} compact={compactNav} />
        <main style={{ flex: 1, overflow: 'hidden', background: '#F7F7F8', display: 'flex', flexDirection: 'column' }}>
          {/* 顶栏 */}
          <div style={{
            height: 48, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
            padding: '0 24px',
            background: T.white,
            borderBottom: `1px solid ${T.gray100}`,
          }}>
            <NotificationBell />
          </div>
          <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            {children}
          </div>
        </main>
      </div>
    </AppContext.Provider>
  );
}
