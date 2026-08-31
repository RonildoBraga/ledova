import { expect, test } from '@playwright/test';

test('renders the signed-out dashboard without runtime errors', async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];

  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.route('**/api/auth/verify/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ valid: false }),
    }),
  );

  await page.goto('/signin');

  await expect(page.getByRole('heading', { name: 'Welcome Back' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  await page.waitForTimeout(500);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('keeps sign-in usable when auth verification fails', async ({ page }) => {
  let verifyRequests = 0;

  await page.route('**/api/auth/verify/', (route) => {
    verifyRequests += 1;
    return route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Temporarily unavailable' }),
    });
  });

  await page.goto('/signin');

  await expect(page.getByRole('heading', { name: 'Welcome Back' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  await page.waitForTimeout(500);

  expect(verifyRequests).toBe(1);
});
