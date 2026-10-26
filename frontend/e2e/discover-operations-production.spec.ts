import { expect, test } from '@playwright/test';

// Rardar refocus retires dedicated operations; assert the real routes do not
// mount the former controls or poll/start their APIs, including for admins.
for (const [path, title] of [['discover', 'Discover'], ['news', '热点资讯'], ['candidates', '候选池'], ['watchlist', '观察列表']]) {
  for (const admin of [false, true]) {
    test(`${path} paused route does not execute work (admin=${admin})`, async ({ page, context }) => {
      if (admin) await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
      let operations = 0;
      await page.route('**/api/v1/rardar/**/operations**', async route => { operations++; await route.fulfill({ json: {} }); });
      await page.goto('/' + path);
      await expect(page.getByRole('heading', { name: title + '已暂停' })).toBeVisible();
      await expect(page.locator('main').getByRole('button')).toHaveCount(0);
      await expect(page.getByRole('button', { name: '退出登录', exact: true })).toHaveCount(0);
      await expect(page.getByRole('link', { name: '打开 TopicEye 管理后台', exact: true })).toHaveAttribute('href', '/admin');
      await page.reload();
      expect(operations).toBe(0);
    });
  }
}
