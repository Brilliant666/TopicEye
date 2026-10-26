import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '@/app/login/page';

const state = vi.hoisted(() => ({ rardarEnabled: true, effects: [] as Array<() => unknown>, oauthProviders: vi.fn() }));
// Run the component's real mount effects explicitly in the repository's node
// environment; React DOM SSR still supplies the real state/memo hooks.
vi.mock('react', async (original) => ({ ...await original<typeof import('react')>(), useEffect: (effect: () => unknown) => { state.effects.push(effect); } }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/providers/AuthProvider', () => ({ useAuthContext: () => ({ currentUser: null, applyAuthSession: vi.fn() }) }));
vi.mock('@/lib/product-profile', () => ({ activeProductProfile: state }));
vi.mock('@/lib/api', () => ({ authApi: { oauthProviders: state.oauthProviders } }));
beforeEach(() => {
  state.effects.length = 0;
  state.oauthProviders.mockReset().mockResolvedValue({ providers: ['google', 'github'] });
});

describe('existing-account password login boundary', () => {
  it('does not request protected OAuth discovery or expose OAuth/registration in Rardar', async () => {
    state.rardarEnabled = true;
    const html = renderToStaticMarkup(<LoginPage />);
    for (const effect of state.effects) effect();
    await Promise.resolve();
    expect(state.oauthProviders).not.toHaveBeenCalled();
    expect(html).not.toContain('使用 Google 登录');
    expect(html).not.toContain('使用 GitHub 登录');
    expect(html).not.toContain('>注册<');
    expect(html).toContain('输入密码');
  });

  it('preserves TopicEye OAuth discovery and registration independently', async () => {
    state.rardarEnabled = false;
    const html = renderToStaticMarkup(<LoginPage />);
    for (const effect of state.effects) effect();
    await Promise.resolve();
    expect(state.oauthProviders).toHaveBeenCalledOnce();
    expect(html).toContain('>注册<');
  });
});
