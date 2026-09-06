import { test, expect } from '@playwright/test';

test.describe('the built dashboard serves its unauthenticated routes', () => {
  test('signin renders its form', async ({ page }) => {
    await page.goto('/signin');
    await expect(page.locator('form, input[type="email"]').first()).toBeVisible();
    await page.screenshot({ path: 'test-results/signin.png', fullPage: true });
  });

  test('an unknown route renders the not-found page rather than a blank body', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');
    await expect(page.locator('body')).not.toBeEmpty();
    await page.screenshot({ path: 'test-results/not-found.png', fullPage: true });
  });

  test('no console error is raised while loading signin', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/signin');
    await page.waitForLoadState('networkidle');
    expect(errors.filter((text) => !text.includes('Failed to load resource'))).toEqual([]);
  });
});
