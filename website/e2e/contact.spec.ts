import { expect, test } from '@playwright/test';

test('walkthrough invitation reaches approved contact details without submitting anything', async ({ page }, testInfo) => {
  const serviceRequests: string[] = [];
  await page.route('**/*', (route) => {
    const request = route.request();
    if (new URL(request.url()).origin !== 'http://127.0.0.1:4187'
      || ['fetch', 'xhr'].includes(request.resourceType())) {
      serviceRequests.push(request.url());
      return route.abort();
    }
    return route.continue();
  });
  page.on('websocket', (socket) => serviceRequests.push(socket.url()));
  await page.goto('./#/');
  const invitation = page.getByRole('link', { name: 'Request a walkthrough' });
  await invitation.focus();
  await invitation.press('Enter');
  await expect(page).toHaveURL(/#\/about#contact$/);
  const contact = page.getByRole('region', { name: 'See LOB Arena in action' });
  await expect(contact).toBeFocused();
  await expect(contact.getByRole('heading')).toBeInViewport();
  await expect(contact).toContainText('guided walkthrough of the research platform');
  const address = contact.getByRole('link', { name: 'alexey.khabalov@gmail.com', exact: true });
  const destination = new URL((await address.getAttribute('href'))!);
  expect(destination.protocol).toBe('mailto:');
  expect(destination.pathname).toBe('alexey.khabalov@gmail.com');
  expect(destination.searchParams.get('subject')).toBe('LOB Arena walkthrough request');
  expect(destination.searchParams.get('body')).toContain('Organization:');
  expect(destination.searchParams.get('body')).toContain("What I'd like to explore:");
  await expect(contact.getByRole('link', { name: 'Alexey Khabalov on LinkedIn' }))
    .toHaveAttribute('href', 'https://www.linkedin.com/in/khabalov/');
  await expect(page.locator('form')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('walkthrough-contact.png'), fullPage: true });
  await page.reload();
  await expect(contact).toBeFocused();
  await expect(contact.getByRole('heading')).toBeInViewport();
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Put detection');
  expect(serviceRequests).toEqual([]);
});
