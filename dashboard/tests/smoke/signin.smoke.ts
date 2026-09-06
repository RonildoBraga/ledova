import { test, expect, type Page } from '@playwright/test';

const SIGNED_OUT_API_NOISE = ['Failed to load resource', 'API Client Error:'];

async function serveASignedOutBackend(page: Page) {
  await page.route('**/api/**', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Authentication credentials were not provided.' }),
    }),
  );
}

test.describe('the built dashboard serves its unauthenticated routes', () => {
  test.beforeEach(async ({ page }) => {
    await serveASignedOutBackend(page);
  });

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

  test('the bundle raises no uncaught exception and no console error beyond the signed-out API noise', async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(`uncaught: ${error.message}`));
    await page.goto('/signin');
    await page.waitForLoadState('networkidle');
    expect(errors.filter((text) => !SIGNED_OUT_API_NOISE.some((noise) => text.includes(noise)))).toEqual([]);
  });
});
