import { expect, test } from '@playwright/test';

test('all six routes load directly and survive refresh without runtime service requests', async ({ page }, testInfo) => {
  const errors: string[] = [];
  const disallowed: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('websocket', (socket) => disallowed.push(socket.url()));
  await page.route('**/*', (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== 'http://127.0.0.1:4187' || ['fetch', 'xhr'].includes(request.resourceType())) {
      disallowed.push(request.url());
      return route.abort();
    }
    return route.continue();
  });
  const routes = [
    ['', 'Put detection'], ['demo', 'Follow the sequence.'], ['research', 'Evidence before claims.'],
    ['architecture', 'A traceable path'], ['detectors', 'A baseline.'], ['about', 'Built to make research'],
  ];
  for (const [path, title] of routes) {
    await page.goto(`./#/${path}`);
    await page.reload();
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title);
    await expect(page).toHaveTitle(/LOB Arena/);
    await expect(page.locator('main')).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`${path || 'home'}.png`), fullPage: true });
  }
  expect(disallowed).toEqual([]);
  expect(errors).toEqual([]);
});

test('replay controls reveal evidence, stop at the end and reset on scenario change', async ({ page }) => {
  await page.goto('./#/demo');
  await expect(page.getByTestId('current-event')).toHaveText('Balanced opening book');
  await page.getByRole('button', { name: 'Step', exact: true }).click();
  await expect(page.getByTestId('current-event')).toHaveText('Small buy order added');
  await page.getByRole('slider').press('End');
  await page.getByRole('slider').press('ArrowLeft');
  await page.getByRole('slider').press('ArrowLeft');
  await expect(page.getByText('Illustrative flag', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Complete', { timeout: 5000 });
  await expect(page.getByRole('button', { name: 'Step', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Replay', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Playing');
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Paused');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByRole('slider')).toHaveValue('0');
  await page.getByRole('combobox', { name: 'Scenario' }).selectOption('1');
  await page.getByRole('slider').press('End');
  await expect(page.getByText('No illustrative flag', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Scenario' }).selectOption('0');
  await expect(page.getByRole('slider')).toHaveValue('0');
  await expect(page.getByRole('status')).toContainText('Paused');
  await expect(page.getByRole('row')).toHaveCount(2);
});

test('navigation, browser history and unknown routes work', async ({ page }, testInfo) => {
  await page.goto('./#/');
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Open menu' }).click();
  await page.getByRole('navigation').getByRole('link', { name: '03 Research' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Evidence before claims.');
  if (testInfo.project.name === 'mobile') await expect(page.getByRole('button', { name: 'Open menu' })).toHaveAttribute('aria-expanded', 'false');
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Put detection');
  await page.goto('./#/missing');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('outside the arena');
  await page.getByRole('link', { name: 'Back to Home' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Put detection');
});

test('research boundaries and keyboard-operated replay remain visible offline', async ({ page, context }) => {
  await page.goto('./#/research');
  await expect(page.getByText('research_baseline_qualified', { exact: true })).toBeVisible();
  await page.goto('./#/detectors');
  await expect(page.getByText(/before GPU training/)).toBeVisible();
  await expect(page.getByText(/Near-real-time detection is a target, not a production capability/)).toBeVisible();
  await page.goto('./#/demo');
  await expect(page.getByRole('slider')).toBeVisible();
  await context.setOffline(true);
  await page.getByRole('slider').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('slider')).toHaveValue('1');
  await page.getByRole('button', { name: 'Reset', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('slider')).toHaveValue('0');
});
