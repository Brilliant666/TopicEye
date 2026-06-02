'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import NotificationBell from '@/components/NotificationBell';
import { authApi, getAuthToken, setAuthToken, sourcesApi, contentsApi, favoritesApi } from '@/lib/api';
import {
  favoriteItemToTargetKey,
  getContentFavoriteKey,
  getFavoriteTargetKey,
  type FavoriteCreatePayload,
  type FavoriteTargetRef,
} from '@/lib/favorites';
import type { AuthTokenResponse, AuthUser } from '@/types';

// App context - shared across pages
interface AppContextType {
  currentUser: AuthUser | null;
  authLoading: boolean;
  favorites: Set<number>;
  favoritePendingIds: Set<number>;
  favoriteTargets: Set<string>;
  favoriteTargetPendingKeys: Set<string>;
  topicCount: number;
  isFavoriteTarget: (target: FavoriteTargetRef) => boolean;
  applyAuthSession: (session: AuthTokenResponse) => void;
  logout: () => Promise<void>;
  toggleFavoriteTarget: (target: FavoriteCreatePayload, options?: { throwOnError?: boolean }) => Promise<boolean>;
  toggleFavorite: (id: number, options?: { throwOnError?: boolean }) => Promise<boolean>;
  refreshCounts: () => void;
}

const AppContext = createContext<AppContextType>({
  currentUser: null,
  authLoading: true,
  favorites: new Set(),
  favoritePendingIds: new Set(),
  favoriteTargets: new Set(),
  favoriteTargetPendingKeys: new Set(),
  topicCount: 0,
  isFavoriteTarget: () => false,
  applyAuthSession: () => {},
  logout: async () => {},
  toggleFavoriteTarget: async () => false,
  toggleFavorite: async () => false,
  refreshCounts: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

const FAVORITES_STORAGE_KEY = 'topiceye_favorites';
const FAVORITE_TARGETS_STORAGE_KEY = 'topiceye_favorite_targets';

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

function loadFavoriteTargetsFromStorage(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = localStorage.getItem(FAVORITE_TARGETS_STORAGE_KEY);
    if (!raw) return new Set();
    const arr: string[] = JSON.parse(raw);
    return new Set(arr.filter((item) => typeof item === 'string' && item.includes(':')));
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

function saveFavoriteTargetsToStorage(favSet: Set<string>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(FAVORITE_TARGETS_STORAGE_KEY, JSON.stringify([...favSet]));
  } catch {}
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [favoritePendingIds, setFavoritePendingIds] = useState<Set<number>>(new Set());
  const favoritePendingRef = useRef<Set<number>>(new Set());
  const [favoriteTargets, setFavoriteTargets] = useState<Set<string>>(new Set());
  const [favoriteTargetIds, setFavoriteTargetIds] = useState<Map<string, number>>(new Map());
  const [favoriteTargetPendingKeys, setFavoriteTargetPendingKeys] = useState<Set<string>>(new Set());
  const favoriteTargetPendingRef = useRef<Set<string>>(new Set());
  const [contentCount, setContentCount] = useState(0);
  const [sourceCount, setSourceCount] = useState(0);
  const [favoriteTotal, setFavoriteTotal] = useState(0);
  const [compactNav, setCompactNav] = useState(false);

  const applyAuthSession = useCallback((session: AuthTokenResponse) => {
    setAuthToken(session.access_token);
    setCurrentUser(session.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      if (getAuthToken()) {
        await authApi.logout();
      }
    } catch {
      // Local logout should still clear stale or invalid sessions.
    } finally {
      setAuthToken(null);
      setCurrentUser(null);
    }
  }, []);

  const refreshCounts = useCallback(async () => {
    try {
      const [contents, sources, allFavorites] = await Promise.all([
        contentsApi.list({ page_size: 1 }),
        sourcesApi.list(),
        favoritesApi.list({ page_size: 200 }),
      ]);
      setContentCount(contents.total || 0);
      setSourceCount(sources.total || sources.items?.length || 0);
      setFavoriteTotal(allFavorites.total || 0);

      const targetKeys = new Set<string>();
      const targetIds = new Map<string, number>();
      const contentIds = new Set<number>();
      for (const item of allFavorites.items || []) {
        const key = favoriteItemToTargetKey(item);
        targetKeys.add(key);
        targetIds.set(key, item.id);
        if (item.target_type === 'content' && item.target_id) {
          contentIds.add(item.target_id);
        }
      }
      setFavoriteTargets(targetKeys);
      setFavoriteTargetIds(targetIds);
      setFavorites(contentIds);
    } catch {}
  }, []);

  useEffect(() => {
    const storedFavorites = loadFavoritesFromStorage();
    setFavorites(storedFavorites);
    setFavoriteTargets((prev) => {
      const next = new Set([...loadFavoriteTargetsFromStorage(), ...prev]);
      for (const id of storedFavorites) {
        next.add(getContentFavoriteKey(id));
      }
      return next;
    });
    void refreshCounts();
  }, [refreshCounts]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const token = getAuthToken();
      if (!token) {
        setAuthLoading(false);
        return;
      }
      try {
        const user = await authApi.me();
        if (!cancelled) setCurrentUser(user);
      } catch {
        setAuthToken(null);
        if (!cancelled) setCurrentUser(null);
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, []);

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

  useEffect(() => {
    saveFavoriteTargetsToStorage(favoriteTargets);
  }, [favoriteTargets]);

  const isFavoriteTarget = useCallback((target: FavoriteTargetRef): boolean => {
    try {
      return favoriteTargets.has(getFavoriteTargetKey(target));
    } catch {
      return false;
    }
  }, [favoriteTargets]);

  const toggleFavoriteTarget = useCallback(async (
    target: FavoriteCreatePayload,
    options?: { throwOnError?: boolean },
  ): Promise<boolean> => {
    const key = getFavoriteTargetKey(target);
    if (favoriteTargetPendingRef.current.has(key)) {
      return favoriteTargets.has(key);
    }

    const wasFavorited = favoriteTargets.has(key);
    favoriteTargetPendingRef.current.add(key);
    setFavoriteTargetPendingKeys((prev) => new Set(prev).add(key));

    try {
      if (wasFavorited) {
        let favoriteId = favoriteTargetIds.get(key);
        if (!favoriteId) {
          const state = await favoritesApi.state({
            target_type: target.target_type,
            target_ids: target.target_id !== undefined && target.target_id !== null ? [target.target_id] : undefined,
            target_keys: target.target_key ? [target.target_key] : undefined,
          });
          favoriteId = state.items.find((item) => item.is_favorited)?.favorite_id || undefined;
        }
        if (!favoriteId) {
          throw new Error('收藏记录不存在，请刷新后重试');
        }
        await favoritesApi.delete(favoriteId);
        setFavoriteTargets((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
        setFavoriteTargetIds((prev) => {
          const next = new Map(prev);
          next.delete(key);
          return next;
        });
        if (target.target_type === 'content' && target.target_id) {
          setFavorites((prev) => {
            const next = new Set(prev);
            next.delete(target.target_id as number);
            return next;
          });
        }
        setFavoriteTotal((prev) => Math.max(0, prev - 1));
        return false;
      }

      const item = await favoritesApi.create(target);
      const itemKey = favoriteItemToTargetKey(item);
      setFavoriteTargets((prev) => new Set(prev).add(itemKey));
      setFavoriteTargetIds((prev) => new Map(prev).set(itemKey, item.id));
      if (item.target_type === 'content' && item.target_id) {
        setFavorites((prev) => new Set(prev).add(item.target_id as number));
      }
      setFavoriteTotal((prev) => prev + 1);
      return true;
    } catch (err) {
      console.error('Toggle favorite target failed:', err);
      if (options?.throwOnError) {
        throw err;
      }
      return favoriteTargets.has(key);
    } finally {
      favoriteTargetPendingRef.current.delete(key);
      setFavoriteTargetPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }, [favoriteTargetIds, favoriteTargets]);

  const toggleFavorite = useCallback(async (id: number, options?: { throwOnError?: boolean }): Promise<boolean> => {
    const targetKey = getContentFavoriteKey(id);
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
      setFavoriteTargets((prev) => {
        const next = new Set(prev);
        if (result.is_favorited) {
          next.add(targetKey);
        } else {
          next.delete(targetKey);
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
    <AppContext.Provider
      value={{
        currentUser,
        authLoading,
        favorites,
        favoritePendingIds,
        favoriteTargets,
        favoriteTargetPendingKeys,
        topicCount: contentCount,
        isFavoriteTarget,
        applyAuthSession,
        logout,
        toggleFavoriteTarget,
        toggleFavorite,
        refreshCounts,
      }}
    >
      <div className="flex h-dvh overflow-hidden">
        <Sidebar
          topicCount={contentCount}
          favCount={favoriteTotal}
          sourceCount={sourceCount}
          compact={compactNav}
          currentUser={currentUser}
          authLoading={authLoading}
          onLogout={logout}
        />
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
