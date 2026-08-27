const repositoryPattern = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

export function parsePublicGitHubRepositoryUrl(value: unknown): { url: string; repository: string } | null {
  if (typeof value !== 'string' || value.length > 300) return null;
  try {
    const parsed = new URL(value);
    if (
      parsed.protocol !== 'https:'
      || parsed.hostname !== 'github.com'
      || parsed.port
      || parsed.username
      || parsed.password
      || parsed.search
      || parsed.hash
    ) return null;
    const parts = parsed.pathname.split('/').filter(Boolean);
    const repository = parts.join('/');
    if (parts.length !== 2 || !repositoryPattern.test(repository)) return null;
    return { url: `https://github.com/${repository}`, repository };
  } catch {
    return null;
  }
}
