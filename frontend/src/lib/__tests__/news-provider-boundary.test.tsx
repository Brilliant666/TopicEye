import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ClientLayout from '@/components/ClientLayout';
import RardarNewsOperations from '@/components/RardarNewsOperations';
import type { AuthUser } from '@/types';

vi.mock('next/navigation', () => ({ usePathname: () => '/news', useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }) }));
vi.mock('@/lib/product-profile', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/product-profile')>(),
  activeProductProfile: { rardarEnabled: true },
}));

describe('actual News authentication provider boundary', () => {
  it.each([null, { id: 1, role: 'admin' } as AuthUser, { id: 2, role: 'user' } as AuthUser])('renders through ClientLayout with actual AuthProvider for %j', (user) => {
    const html = renderToStaticMarkup(
      <ClientLayout initialData={{ user, featureFlags: {}, counts: null }}>
        <p>Saved news remains readable</p>
        <RardarNewsOperations source={null} topic={null} sort="balanced" page={1} itemCount={18} />
      </ClientLayout>,
    );
    expect(html).toContain('Saved news remains readable');
    expect(html).toContain('data-rardar-shell="true"');
    if (user?.role === 'admin') expect(html).toContain('补充中文速读');
    else expect(html).not.toContain('确认补充中文');
  });
});
