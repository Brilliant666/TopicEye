const RARDAR_NAVIGATION = Object.freeze([
  Object.freeze({ href: '/', label: '今日' }),
  Object.freeze({ href: '/activity', label: '动态' }),
  Object.freeze({ href: '/discover', label: '发现' }),
  Object.freeze({ href: '/find', label: '找项目' }),
  Object.freeze({ href: '/candidates', label: '候选池' }),
  Object.freeze({ href: '/watchlist', label: '观察列表' }),
]);

const RARDAR_INTERNAL_HOME = '/rardar-foundation';
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

function matchesPath(pathname, route) {
  if (route === '/') return pathname === '/';
  return pathname === route || pathname.startsWith(`${route}/`);
}

function rardarRouteVisibility(pathname) {
  if (pathname === RARDAR_INTERNAL_HOME) return RARDAR_ROUTE_VISIBILITY.ALLOW;
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
};
