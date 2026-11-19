import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, access, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { browserEnvironment, copyBrowserSource, origins } from './browser-sandbox.mjs';

test('browser environment drops service secrets and forces the synthetic API and anonymous auth', () => {
  const env = browserEnvironment({ PATH: '/test/bin', HOME: '/test/home',
    DATABASE_URL: 'synthetic-secret', OPENAI_API_KEY: 'synthetic-secret', NODE_OPTIONS: 'synthetic-secret',
    NEXT_PUBLIC_SUPABASE_URL: 'https://synthetic-secret.invalid', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'synthetic-secret',
    INTERNAL_API_BASE_URL: 'https://synthetic-secret.invalid', NEXT_PUBLIC_API_BASE_URL: 'https://synthetic-secret.invalid',
  }, '/test/sandbox', '/test/results');
  assert.equal(env.PATH, '/test/bin');
  assert.equal(env.NEXT_PUBLIC_API_BASE_URL, origins.apiOrigin + '/api/v1');
  assert.equal(env.INTERNAL_API_BASE_URL, origins.apiOrigin + '/api/v1');
  assert.equal(env.NEXT_PUBLIC_SUPABASE_URL, '');
  assert.equal(env.NEXT_PUBLIC_SUPABASE_ANON_KEY, '');
  assert.ok(!JSON.stringify(env).includes('synthetic-secret'));
});

test('browser source copy excludes environment files, caches, unknown roots and symlink targets', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'videomind-copy-test-'));
  const source = path.join(root, 'source'), target = path.join(root, 'target');
  try {
    await mkdir(path.join(source, 'app'), { recursive: true });
    await mkdir(path.join(source, 'public'));
    await mkdir(path.join(source, '.next'));
    await writeFile(path.join(source, 'app/page.tsx'), 'synthetic app');
    await writeFile(path.join(source, 'app/.env.local'), 'synthetic-secret');
    await writeFile(path.join(source, '.env'), 'synthetic-secret');
    await writeFile(path.join(source, '.next/cache'), 'synthetic cache');
    await writeFile(path.join(source, 'private-user-data'), 'synthetic-secret');
    await writeFile(path.join(root, 'outside-secret'), 'synthetic-secret');
    await symlink(path.join(root, 'outside-secret'), path.join(source, 'public/linked-secret'));
    for (const name of ['package.json', 'package-lock.json', 'next-env.d.ts', 'next.config.ts', 'eslint.config.mjs',
      'postcss.config.js', 'tsconfig.json', 'tailwind.config.ts', 'proxy.ts', 'playwright.config.ts']) {
      await writeFile(path.join(source, name), 'synthetic source file');
    }
    await copyBrowserSource(source, target);
    assert.equal(await readFile(path.join(target, 'app/page.tsx'), 'utf8'), 'synthetic app');
    for (const name of ['.env', 'app/.env.local', '.next', 'private-user-data', 'public/linked-secret']) {
      await assert.rejects(access(path.join(target, name)), { code: 'ENOENT' });
    }
  } finally { await rm(root, { recursive: true, force: true }); }
});
