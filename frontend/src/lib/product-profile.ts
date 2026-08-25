import {
  RARDAR_INTERNAL_HOME,
  RARDAR_NAVIGATION,
  RARDAR_ROUTE_VISIBILITY,
  isRardarNavigationActive,
  rardarRouteVisibility,
  resolveProductProfile,
} from '../../product-profile.config.js';

export const activeProductProfile = resolveProductProfile(
  process.env.NEXT_PUBLIC_RARDAR_PRODUCT_MODE,
);

export const isRardarProduct = () => activeProductProfile.rardarEnabled;
export const isTopicEyeProduct = () => !activeProductProfile.rardarEnabled;

export {
  RARDAR_INTERNAL_HOME,
  RARDAR_NAVIGATION,
  RARDAR_ROUTE_VISIBILITY,
  isRardarNavigationActive,
  rardarRouteVisibility,
};
