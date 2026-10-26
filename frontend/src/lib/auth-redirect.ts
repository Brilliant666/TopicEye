/** A login return target is navigation only, never an instruction to run an action. */
export function safeLoginRedirect(value: string | null | undefined): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\r\n]/u.test(value)) return '/';
  try {
    const target = new URL(value, 'https://local.invalid');
    if (target.origin !== 'https://local.invalid' || /^\/(?:login|oauth\/callback)(?:\/|$)/u.test(target.pathname)) return '/';
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return '/';
  }
}

export function loginHrefForPath(path: string): string {
  return `/login?redirect=${encodeURIComponent(safeLoginRedirect(path))}`;
}

export function currentLoginHref(fallback = '/'): string {
  const path = typeof window === 'undefined' ? fallback : `${window.location.pathname}${window.location.search}`;
  return loginHrefForPath(path);
}
