import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('Rardar product profile', () => {
  it('is disabled by default and keeps TopicEye as the upstream product', async () => {
    vi.stubEnv('NEXT_PUBLIC_RARDAR_PRODUCT_MODE', 'false');
    const profile = await import('@/lib/product-profile');
    expect(profile.RARDAR_PRODUCT_MODE).toBe(false);
  });

  it('exposes the approved Rardar information architecture from one profile', async () => {
    vi.stubEnv('NEXT_PUBLIC_RARDAR_PRODUCT_MODE', 'true');
    const profile = await import('@/lib/product-profile');
    expect(profile.RARDAR_PRODUCT_MODE).toBe(true);
    expect(profile.RARDAR_NAVIGATION).toEqual([
      { href: '/', label: '今日' },
      { href: '/signals', label: '动态' },
      { href: '/discover', label: '发现' },
      { href: '/find-project', label: '找项目' },
      { href: '/candidates', label: '候选池' },
      { href: '/watchlist', label: '观察列表' },
    ]);
  });
});
