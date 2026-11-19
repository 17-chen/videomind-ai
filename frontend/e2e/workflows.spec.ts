import { test, expect, type BrowserContext } from '@playwright/test';
import origins from './origins.json';

const note = 'Synthetic persisted notes appeared automatically.';
const issues = new WeakMap<BrowserContext, string[]>();
test.beforeEach(async ({ context, page, request }) => {
  const failures: string[] = [];
  issues.set(context, failures);
  expect((await request.post(origins.apiOrigin + '/__e2e/reset', { data: { mode: 'success' } })).ok()).toBeTruthy();
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (![origins.appOrigin, origins.apiOrigin].includes(url.origin)) {
      failures.push('Unexpected browser origin: ' + url.origin);
      return route.abort();
    }
    if (url.pathname === '/favicon.ico') return route.fulfill({ status: 204 });
    return route.continue();
  });
  page.on('pageerror', error => failures.push(error.message));
  page.on('console', message => { if (message.type() === 'error') failures.push(message.text()); });
});
test.afterEach(async ({ context }) => { expect(issues.get(context)).toEqual([]); });

test('queued job publishes server-rendered notes without a document reload and polling stops', async ({ page, request }) => {
  let documents = 0;
  page.on('request', req => { if (req.isNavigationRequest() && req.frame() === page.mainFrame()) documents++; });
  await page.goto('/videos/browser-video');
  const run = page.getByRole('button', { name: '一键处理并入库', exact: true });
  await run.click();
  await expect(page.getByRole('button', { name: '处理中，请稍候', exact: true })).toBeDisabled();
  await expect(page.locator('pre').filter({ hasText: note })).toBeVisible();
  await expect(run).toBeEnabled();
  expect(documents).toBe(1);
  await page.waitForTimeout(600);
  const before = await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json();
  await page.waitForTimeout(3500); // Longer than the real 3s polling interval.
  const after = await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json();
  expect(after.taskReads).toBe(before.taskReads);
  expect(after.runCalls).toBe(1);
  expect(after.credentialAttempts).toBe(0);
  expect(after.observedStatuses).toEqual(expect.arrayContaining(['queued', 'completed']));
});

test('background failure unlocks an explicit retry which then refreshes the notes', async ({ page, request }) => {
  await request.post(origins.apiOrigin + '/__e2e/reset', { data: { mode: 'fail-once' } });
  await page.goto('/videos/browser-video');
  await page.getByRole('button', { name: '一键处理并入库', exact: true }).click();
  const retry = page.getByRole('button', { name: '从中断处继续', exact: true });
  await expect(retry).toBeEnabled();
  await expect(page.getByText('Synthetic background failure', { exact: true }).first()).toBeVisible();
  await expect(page.locator('pre').filter({ hasText: note })).toHaveCount(0);
  expect((await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json()).runCalls).toBe(1);
  await retry.click();
  await expect(page.locator('pre').filter({ hasText: note })).toBeVisible();
  expect((await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json()).runCalls).toBe(2);
});

test('queued cancellation reaches a terminal unlocked view without notes', async ({ page, request }) => {
  await page.goto('/videos/browser-video');
  await page.getByRole('button', { name: '一键处理并入库', exact: true }).click();
  await page.getByRole('button', { name: '取消任务', exact: true }).click();
  await expect(page.getByRole('button', { name: '一键处理并入库', exact: true })).toBeEnabled();
  await expect(page.locator('pre').filter({ hasText: note })).toHaveCount(0);
  const metrics = await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json();
  expect(metrics.runCalls).toBe(1);
  expect(metrics.cancelCalls).toBe(1);
});

test('one chat request preserves the submitted question and its citation opens the correct video', async ({ page, request }) => {
  await page.goto('/chat');
  const input = page.getByRole('textbox');
  await input.fill('Synthetic browser question');
  await page.locator('form').evaluate((form: HTMLFormElement) => { form.requestSubmit(); form.requestSubmit(); });
  await expect(page.getByRole('button', { name: '询问记忆', exact: true })).toBeDisabled();
  await input.fill('Synthetic next draft');
  const citation = page.locator('a[aria-label="[1] Synthetic browser video"]');
  await expect(citation).toBeVisible();
  await expect(page.getByText('回答的问题：Synthetic browser question', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('Synthetic next draft');
  await expect(citation).toHaveAttribute('href', '/videos/browser-video');
  expect((await (await request.get(origins.apiOrigin + '/__e2e/metrics')).json()).chatCalls).toBe(1);
  await expect(page.getByRole('link', { name: '[99]', exact: true })).toHaveCount(0);
  await citation.click();
  await expect(page).toHaveURL(origins.appOrigin + '/videos/browser-video');
  await expect(page.getByRole('heading', { name: 'Synthetic browser video', exact: true })).toBeVisible();
});
