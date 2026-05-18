'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { sourcesApi, contentsApi } from '@/lib/api';

// App context - shared across pages
interface AppContextType {
  favorites: Set<number>;
  toggleFavorite: (id: number) => void;
  refreshCounts: () => void;
}

const AppContext = createContext<AppContextType>({
  favorites: new Set(),
  toggleFavorite: () => {},
  refreshCounts: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [contentCount, setContentCount] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);

  const refreshCounts = useCallback(async () => {
    try {
      const [contents, sources] = await Promise.all([
        contentsApi.list({ page_size: 1 }),
        sourcesApi.list(),
      ]);
      setContentCount(contents.total || 0);
      setSourceCount((sources as any).total || (sources as any).items?.length || 0);

      // Also refresh favorites from backend
      const favs = await contentsApi.listFavorites({ page_size: 100 });
      const favIds = new Set((favs.items || []).map((item: any) => item.id));
      setFavorites(favIds);
    } catch {}
  }, []);

  useEffect(() => {
    refreshCounts();
  }, [refreshCounts]);

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
    <AppContext.Provider value={{ favorites, toggleFavorite, refreshCounts }}>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        <Sidebar topicCount={contentCount} favCount={favorites.size} sourceCount={sourceCount} />
        <main style={{ flex: 1, overflow: 'hidden', background: '#F7F7F8' }}>
          {children}
        </main>
      </div>
    </AppContext.Provider>
  );
}
