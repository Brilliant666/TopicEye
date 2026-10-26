import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { prefetchInitialData } from '@/lib/server-prefetch';

const state = vi.hoisted(() => ({ token: '', rardarEnabled: true }));
vi.mock('next/headers', () => ({ cookies: async () => ({ get: () => state.token ? { value: state.token } : undefined }) }));
vi.mock('@/lib/product-profile', () => ({ activeProductProfile: state }));
beforeEach(() => { state.token = ''; state.rardarEnabled = true; });
afterEach(() => vi.unstubAllGlobals());

it('performs no authentication or private prefetch for anonymous public readers', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  expect(await prefetchInitialData()).toEqual({ user: null, featureFlags: {}, counts: null });
  expect(fetcher).not.toHaveBeenCalled();
});

it.each(['user', 'admin'])('loads only lightweight identity and necessary admin flags for Rardar %s', async (role) => {
  state.token = 'synthetic-session';
  const fetcher = vi.fn(async (path: string) => new Response(JSON.stringify(path.endsWith('/auth/me') ? { id: 42, role } : { flags: { test: true } }), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  const data = await prefetchInitialData();
  expect(data.user).toMatchObject({ id: 42, role });
  expect(data.counts).toBeNull();
  expect(fetcher.mock.calls.map(([path]) => new URL(path).pathname)).toEqual(role === 'admin' ? ['/api/v1/auth/me', '/api/v1/settings/feature-flags'] : ['/api/v1/auth/me']);
});

it('preserves TopicEye sidebar prefetch independently of Rardar mode', async () => {
  state.token = 'synthetic-session'; state.rardarEnabled = false;
  const fetcher = vi.fn(async (path: string) => new Response(JSON.stringify(path.endsWith('/auth/me') ? { id: 42, role: 'user' } : {}), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  expect((await prefetchInitialData()).counts).toEqual({ todayPicks: 0, sourceCount: 0, favoriteTotal: 0 });
  expect(fetcher.mock.calls.map(([path]) => new URL(path).pathname)).toEqual(expect.arrayContaining(['/api/v1/contents/today-count', '/api/v1/sources/me', '/api/v1/favorites']));
});
