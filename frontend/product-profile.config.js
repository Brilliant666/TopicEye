const RARDAR_NAVIGATION = Object.freeze([
  Object.freeze({ href: '/', label: '今日热榜' }),
  Object.freeze({ href: '/historical-hot', label: '历史回顾' }),
  Object.freeze({ href: '/find', label: '找项目' }),
  Object.freeze({ href: '/activity', label: '动态' }),
]);

const RARDAR_INTERNAL_HOME = '/rardar-foundation';
const TOPICEYE_PROXY_TIMEOUT_MS = 120000;
const RARDAR_PROXY_TIMEOUT_MS = 300000;
const RARDAR_ROUTE_VISIBILITY = Object.freeze({
  ALLOW: 'ALLOW',
  HIDE_FROM_NAV: 'HIDE_FROM_NAV',
  REDIRECT: 'REDIRECT',
  NOT_FOUND: 'NOT_FOUND',
});

function parseRardarProductMode(value) {
  if (value === undefined || value === null || value === '') return false;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true') return true;
    if (normalized === 'false' || normalized === '') return false;
  }
  throw new Error('RARDAR_PRODUCT_MODE must be the literal "true" or "false"');
}

function resolveProductProfile(value) {
  const rardarEnabled = parseRardarProductMode(value);
  return Object.freeze(
    rardarEnabled
      ? {
          key: 'rardar',
          name: 'Rardar',
          rardarEnabled: true,
          navigation: RARDAR_NAVIGATION,
        }
      : {
          key: 'topiceye',
          name: 'TopicEye',
          rardarEnabled: false,
          navigation: Object.freeze([]),
        },
  );
}

function resolveProxyTimeoutMs(value) {
  return parseRardarProductMode(value) ? RARDAR_PROXY_TIMEOUT_MS : TOPICEYE_PROXY_TIMEOUT_MS;
}

function matchesPath(pathname, route) {
  if (route === '/') return pathname === '/';
  return pathname === route || pathname.startsWith(`${route}/`);
}

function rardarRouteVisibility(pathname) {
  if (pathname === RARDAR_INTERNAL_HOME) return RARDAR_ROUTE_VISIBILITY.ALLOW;
  if (matchesPath(pathname, '/project/github')) return RARDAR_ROUTE_VISIBILITY.ALLOW;
  if (matchesPath(pathname, '/project/stable')) return RARDAR_ROUTE_VISIBILITY.ALLOW;
  if (['/news', '/discover', '/candidates', '/watchlist'].includes(pathname)) return RARDAR_ROUTE_VISIBILITY.ALLOW;
  if (RARDAR_NAVIGATION.some((item) => matchesPath(pathname, item.href))) {
    return RARDAR_ROUTE_VISIBILITY.ALLOW;
  }
  if (
    matchesPath(pathname, '/admin') ||
    matchesPath(pathname, '/login') ||
    matchesPath(pathname, '/oauth/callback')
  ) {
    return RARDAR_ROUTE_VISIBILITY.HIDE_FROM_NAV;
  }
  return RARDAR_ROUTE_VISIBILITY.REDIRECT;
}

function isRardarNavigationActive(pathname, href) {
  if (href === '/') return pathname === '/' || pathname === RARDAR_INTERNAL_HOME;
  return matchesPath(pathname, href);
}

module.exports = {
  RARDAR_INTERNAL_HOME,
  RARDAR_NAVIGATION,
  RARDAR_ROUTE_VISIBILITY,
  isRardarNavigationActive,
  parseRardarProductMode,
  rardarRouteVisibility,
  resolveProductProfile,
  resolveProxyTimeoutMs,
};
