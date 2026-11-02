import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { checkDeployment, publicOrigin } from './check-deployment.mjs';

const valid = {
  NEXT_PUBLIC_APP_URL: 'https://app.example.com',
  NEXT_PUBLIC_VERCEL_URL: 'synthetic-preview.vercel.app',
  NEXT_PUBLIC_API_BASE_URL: 'https://api.example.com/api/v1',
  NEXT_PUBLIC_SUPABASE_URL: 'https://project.example.com',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: 'sb_publishable_synthetic_public_key',
};

test('configuration success never claims real service acceptance', () => {
  const result = checkDeployment(valid);
  assert.equal(result.status, 'configuration_passed');
  assert.equal(result.ready_for_public_users, false);
  assert.equal(Object.values(valid).some(value => JSON.stringify(result).includes(value)), false);
});

test('missing configuration, wrong routes and service keys block deployment', () => {
  for (const env of [{}, { ...valid, NEXT_PUBLIC_API_BASE_URL: 'https://api.example.com' },
    { ...valid, NEXT_PUBLIC_SUPABASE_ANON_KEY: 'sb_secret_private' },
    { ...valid, NEXT_PUBLIC_SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.synthetic' },
    { ...valid, INTERNAL_API_BASE_URL: 'http://backend:8000/api/v1' }]) {
    assert.equal(checkDeployment(env).status, 'blocked');
  }
});

test('wildcard, local, userinfo and malformed origins are rejected', () => {
  for (const value of ['http://app.example.com', 'https://localhost', 'https://127.1',
    'https://*.example.com', 'https://user:secret@app.example.com', 'https://app.example.com/private',
    'https://app.example.com:bad', 'https://[bad', 'https://app.example.com\n']) {
    assert.equal(publicOrigin(value), false);
  }
});

test('CLI rejects accidentally public secrets without echoing values', () => {
  const env = { ...process.env, ...valid, NEXT_PUBLIC_OWNER_API_KEY: 'private-sentinel-value' };
  const result = spawnSync(process.execPath, ['scripts/check-deployment.mjs'], { env, encoding: 'utf8' });
  assert.equal(result.status, 2);
  assert.equal(JSON.parse(result.stdout).checks.public_variables_allowlist, false);
  assert.equal(result.stdout.includes('private-sentinel-value'), false);
  assert.equal(result.stderr, '');
});
