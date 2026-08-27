import { describe, expect, it } from 'vitest';

import { parsePublicGitHubRepositoryUrl } from '@/lib/rardar-repository-url';

describe('Rardar repository URL prefill', () => {
  it('keeps one canonical public repository URL refresh-safe', () => {
    expect(parsePublicGitHubRepositoryUrl('https://github.com/owner/repository')).toEqual({
      url: 'https://github.com/owner/repository',
      repository: 'owner/repository',
    });
  });

  it.each([
    'http://github.com/owner/repository',
    'https://github.com/owner/repository/issues',
    'https://github.com/owner/repository?tab=readme',
    'https://user:password@github.com/owner/repository',
    'https://evil.example/owner/repository',
    'https://github.com/owner/%2e%2e/repository',
  ])('rejects unsafe or non-repository URL %s', (value) => {
    expect(parsePublicGitHubRepositoryUrl(value)).toBeNull();
  });
});
