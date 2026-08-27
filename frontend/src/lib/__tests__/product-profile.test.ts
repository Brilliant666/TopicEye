import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  RARDAR_INTERNAL_HOME,
  RARDAR_NAVIGATION,
  RARDAR_ROUTE_VISIBILITY,
  isRardarNavigationActive,
  parseRardarProductMode,
  rardarRouteVisibility,
  resolveProductProfile,
  resolveProxyTimeoutMs,
} from '../../../product-profile.config.js';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('product profile contract', () => {
  it.each([undefined, '', false, 'false', ' FALSE '])(
    'defaults or explicitly disables Rardar for %s',
    (value) => {
      expect(parseRardarProductMode(value)).toBe(false);
      expect(resolveProductProfile(value)).toMatchObject({
        key: 'topiceye',
        name: 'TopicEye',
        rardarEnabled: false,
      });
    },
  );

  it.each([true, 'true', ' TRUE '])('enables Rardar only for %s', (value) => {
    expect(parseRardarProductMode(value)).toBe(true);
    expect(resolveProductProfile(value)).toMatchObject({
      key: 'rardar',
      name: 'Rardar',
      rardarEnabled: true,
      navigation: RARDAR_NAVIGATION,
    });
  });

  it.each(['1', 'yes', 'enabled', 'rardar', 1])('fails closed for invalid value %s', (value) => {
    expect(() => parseRardarProductMode(value)).toThrow(/literal "true" or "false"/);
  });

  it('keeps the approved navigation in one ordered contract', () => {
    expect(RARDAR_NAVIGATION).toEqual([
      { href: '/', label: '今日' },
      { href: '/activity', label: '动态' },
      { href: '/discover', label: '发现' },
      { href: '/find', label: '找项目' },
      { href: '/candidates', label: '候选池' },
      { href: '/watchlist', label: '观察列表' },
    ]);
  });

  it('allows the Rardar shell, isolates admin/system routes, and redirects legacy content', () => {
    expect(rardarRouteVisibility('/')).toBe(RARDAR_ROUTE_VISIBILITY.ALLOW);
    expect(rardarRouteVisibility('/find')).toBe(RARDAR_ROUTE_VISIBILITY.ALLOW);
    expect(rardarRouteVisibility(RARDAR_INTERNAL_HOME)).toBe(RARDAR_ROUTE_VISIBILITY.ALLOW);
    expect(rardarRouteVisibility('/admin/sources')).toBe(RARDAR_ROUTE_VISIBILITY.HIDE_FROM_NAV);
    expect(rardarRouteVisibility('/login')).toBe(RARDAR_ROUTE_VISIBILITY.HIDE_FROM_NAV);
    expect(rardarRouteVisibility('/trending')).toBe(RARDAR_ROUTE_VISIBILITY.REDIRECT);
  });

  it('maps the internal home rewrite to the visible Today navigation item', () => {
    expect(isRardarNavigationActive(RARDAR_INTERNAL_HOME, '/')).toBe(true);
    expect(isRardarNavigationActive('/activity', '/activity')).toBe(true);
    expect(isRardarNavigationActive('/discover', '/activity')).toBe(false);
  });

  it('keeps TopicEye proxy timing stable and lets Rardar finish its bounded fallback chain', () => {
    expect(resolveProxyTimeoutMs(undefined)).toBe(120_000);
    expect(resolveProxyTimeoutMs('false')).toBe(120_000);
    expect(resolveProxyTimeoutMs('true')).toBe(300_000);
  });

  it('exposes the normalized build value through the frontend profile module', async () => {
    vi.stubEnv('NEXT_PUBLIC_RARDAR_PRODUCT_MODE', 'true');
    const profile = await import('@/lib/product-profile');

    expect(profile.activeProductProfile.key).toBe('rardar');
    expect(profile.isRardarProduct()).toBe(true);
    expect(profile.isTopicEyeProduct()).toBe(false);
  });
});
