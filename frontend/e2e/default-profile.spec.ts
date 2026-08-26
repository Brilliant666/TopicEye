import { expect, test } from '@playwright/test';

test('keeps the default TopicEye product and rejects Rardar-only pages', async ({ page }) => {
  test.skip(process.env.RARDAR_E2E_PROFILE !== 'topiceye', 'requires the default-profile frontend process');
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-product-profile', 'topiceye');
  await expect(page).toHaveTitle(/选题雷达/);
  await page.goto('/rardar-foundation');
  await expect(page.getByText('404')).toBeVisible();
});
