import { defineConfig } from '@playwright/test';
import { realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import origins from './e2e/origins.json';

if (process.env.VIDEOMIND_BROWSER_ISOLATED !== '1' ||
    !realpathSync(process.cwd()).startsWith(path.join(realpathSync(tmpdir()), 'videomind-browser-'))) {
  throw new Error('Use npm run test:e2e; browser checks must run in their temporary copy');
}
const artifacts = process.env.VIDEOMIND_BROWSER_ARTIFACT_DIR!;
export default defineConfig({
  testDir: './e2e', workers: 1, fullyParallel: false, retries: 0, timeout: 45000,
  expect: { timeout: 15000 },
  reporter: [['list'], ['json', { outputFile: path.join(artifacts, 'report.json') }]],
  outputDir: path.join(artifacts, 'results'),
  use: { baseURL: origins.appOrigin, browserName: 'chromium', locale: 'zh-CN',
    serviceWorkers: 'block', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: 'node e2e/synthetic-api.mjs', url: origins.apiOrigin + '/__e2e/ready',
      reuseExistingServer: false, gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 } },
    { command: 'node .next/standalone/server.js',
      env: { ...process.env, HOSTNAME: '127.0.0.1', PORT: new URL(origins.appOrigin).port },
      url: origins.appOrigin + '/auth', reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 } },
  ],
});
