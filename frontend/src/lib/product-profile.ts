export const RARDAR_PRODUCT_MODE =
  process.env.NEXT_PUBLIC_RARDAR_PRODUCT_MODE === 'true';

export const RARDAR_NAVIGATION = [
  { href: '/', label: '今日' },
  { href: '/signals', label: '动态' },
  { href: '/discover', label: '发现' },
  { href: '/find-project', label: '找项目' },
  { href: '/candidates', label: '候选池' },
  { href: '/watchlist', label: '观察列表' },
] as const;

export const RARDAR_PRODUCT_PROFILE = {
  key: 'rardar-poc',
  name: 'Rardar',
  mode: RARDAR_PRODUCT_MODE,
  navigation: RARDAR_NAVIGATION,
} as const;
