import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RardarProjectExplanation from '@/components/RardarProjectExplanation';
import type { AuthUser } from '@/types';

const state = vi.hoisted(() => ({
  user: null as AuthUser | null, authLoading: false,
  values: [null, false, null, false] as unknown[], index: 0,
}));
vi.mock('react', async (original) => {
  const react = await original<typeof import('react')>();
  return { ...react, useState: (initial: unknown) => react.useState(state.index < state.values.length ? state.values[state.index++] : initial) };
});
vi.mock('@/providers/AuthProvider', () => ({ useAuthContext: () => ({ currentUser: state.user, authLoading: state.authLoading }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
beforeEach(() => { state.user = null; state.authLoading = false; state.values = [null, false, null, false]; state.index = 0; });
afterEach(() => vi.unstubAllGlobals());

function renderInsight() {
  return renderToStaticMarkup(<RardarProjectExplanation repository="fixture/saved" generationId="boards-saved" stableId="stable-saved" source="trending" />);
}

describe('visitor AI action controls', () => {
  it.each([
    ['generate', [null, false, null, false], '生成 AI 深度解读'],
    ['retry', [null, false, 'synthetic-unavailable', false], '重试'],
    ['waiting', [null, false, null, true], '稍后重试'],
  ])('disables the anonymous %s action without a login CTA', (_variant, values, label) => {
    state.values = values as unknown[];
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const html = renderInsight();
    const button = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/u)?.[0] || '';
    expect(button).toContain(label);
    expect(button).toContain('disabled=""');
    expect(button).toContain('aria-busy="false"');
    expect(html).toContain('此功能需登录，暂不向访客开放');
    expect(html).not.toContain('href="/login');
    expect(html).not.toContain('登录后生成');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('keeps authentication-pending actions disabled even with a known account', () => {
    state.user = { id: 7, role: 'admin' } as AuthUser; state.authLoading = true;
    const html = renderInsight();
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-busy="false"');
  });

  it('does not mark permanent visitor restriction as generation in progress', () => {
    state.values = [null, true, null, false];
    const html = renderInsight();
    expect(html).toContain('aria-busy="false"');
    expect(html).toContain('生成 AI 深度解读');
    expect(html).not.toContain('正在基于静态证据分析');
  });

  it('keeps the signed-in administrator action enabled and marks actual loading separately', () => {
    state.user = { id: 7, role: 'admin' } as AuthUser;
    expect(renderInsight()).not.toContain('disabled=""');
    state.values = [null, true, null, false]; state.index = 0;
    const html = renderInsight();
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('正在基于静态证据分析');
  });
});
