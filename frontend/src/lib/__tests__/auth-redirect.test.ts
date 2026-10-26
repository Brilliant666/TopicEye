import { afterEach, describe, expect, it, vi } from 'vitest';
import { currentLoginHref, loginHrefForPath, safeLoginRedirect } from '@/lib/auth-redirect';

afterEach(() => vi.unstubAllGlobals());

describe('navigation-only login returns', () => {
  it.each([
    '/project/stable/saved-project?generation=boards-123&history=1',
    '/project/github/42?discoverGeneration=saved%2Bgeneration',
    '/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Fowner%2Frepo&runId=private-id',
  ])('preserves the project/Find target including its original query: %s', (path) => {
    expect(safeLoginRedirect(path)).toBe(path);
    expect(new URL(loginHrefForPath(path), 'https://local.invalid').searchParams.get('redirect')).toBe(path);
    const [pathname, search] = path.split('?');
    vi.stubGlobal('window', { location: { pathname, search: `?${search}` } });
    expect(currentLoginHref()).toBe(loginHrefForPath(path));
  });

  it.each([null, '', 'https://outside.invalid', '//outside.invalid/path', '/\\outside.invalid', '/\nmalformed', '/login?redirect=/find', '/oauth/callback#token=private'])('rejects external, malformed and recursive targets: %s', (path) => {
    expect(safeLoginRedirect(path)).toBe('/');
  });

});
