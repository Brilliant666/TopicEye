import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ClientLayout from '@/components/ClientLayout';
import RardarTodayOperations from '@/components/RardarTodayOperations';
import type { AuthUser } from '@/types';

const state = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => state.pathname, useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/product-profile', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/product-profile')>(),
  activeProductProfile: { rardarEnabled: true },
}));

// Use the real AuthProvider and hook, not a permissive mocked context. Both
// rewrite destination SSR and public-path hydration must share this boundary.
describe.each(['/', '/rardar-foundation'])('actual Today auth provider at %s', (pathname) => {
  it.each([null, { id: 1, role: 'admin' } as AuthUser, { id: 2, role: 'user' } as AuthUser])('renders the real operator component for %j', (user) => {
    state.pathname = pathname;
    const html = renderToStaticMarkup(
      <ClientLayout initialData={{ user, featureFlags: {}, counts: null }}>
        <p>Saved Today facts remain readable</p>
        <RardarTodayOperations syncedAt="2026-09-09T01:00:00Z" />
      </ClientLayout>,
    );
    expect(html).toContain('Saved Today facts remain readable');
    expect(html).toContain('data-rardar-shell="true"');
    if (user?.role === 'admin') expect(html).toContain('检查并同步榜单');
    else expect(html).not.toContain('aria-label="管理员榜单更新"');
  });
});
