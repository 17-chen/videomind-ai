// Validate only configuration shape. Never print env values or claim service acceptance.
import { pathToFileURL } from 'node:url';

export function publicOrigin(value) {
  if (!value || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port
      && url.pathname === '/' && !url.search && !url.hash
      && /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(url.hostname)
      && !/\.(?:localhost|local|internal|invalid)$/.test(url.hostname)
      && !/^\d+(?:\.\d+){3}$/.test(url.hostname);
  } catch { return false; }
}

function publicKey(value = '') {
  if (value.length > 8192) return false;
  if (value.startsWith('sb_publishable_')) return value.length > 'sb_publishable_'.length + 10 && /^[A-Za-z0-9_-]+$/.test(value);
  try {
    const parts = value.split('.');
    return parts.length === 3 && JSON.parse(Buffer.from(parts[1], 'base64url').toString()).role === 'anon';
  } catch { return false; }
}

// Documented Vercel framework metadata is public and injected at build time.
const vercelPublic = new Set([
  'NEXT_PUBLIC_VERCEL_ENV',
  'NEXT_PUBLIC_VERCEL_TARGET_ENV',
  'NEXT_PUBLIC_VERCEL_URL',
  'NEXT_PUBLIC_VERCEL_BRANCH_URL',
  'NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL',
  'NEXT_PUBLIC_VERCEL_HASH_SALT',
  'NEXT_PUBLIC_VERCEL_GIT_PROVIDER',
  'NEXT_PUBLIC_VERCEL_GIT_REPO_SLUG',
  'NEXT_PUBLIC_VERCEL_GIT_REPO_OWNER',
  'NEXT_PUBLIC_VERCEL_GIT_REPO_ID',
  'NEXT_PUBLIC_VERCEL_GIT_COMMIT_REF',
  'NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA',
  'NEXT_PUBLIC_VERCEL_GIT_COMMIT_MESSAGE',
  'NEXT_PUBLIC_VERCEL_GIT_COMMIT_AUTHOR_LOGIN',
  'NEXT_PUBLIC_VERCEL_GIT_COMMIT_AUTHOR_NAME',
  'NEXT_PUBLIC_VERCEL_GIT_PULL_REQUEST_ID',
]);

export function checkDeployment(env) {
  const checks = {
    app_https_origin: publicOrigin(env.NEXT_PUBLIC_APP_URL),
    supabase_https_origin: publicOrigin(env.NEXT_PUBLIC_SUPABASE_URL),
    supabase_public_key_shape: publicKey(env.NEXT_PUBLIC_SUPABASE_ANON_KEY),
    public_variables_allowlist: Object.keys(env).filter(key => key.startsWith('NEXT_PUBLIC_') && !vercelPublic.has(key)).every(key => [
      'NEXT_PUBLIC_APP_URL', 'NEXT_PUBLIC_API_BASE_URL', 'NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY',
    ].includes(key)),
  };
  try {
    const api = new URL(env.NEXT_PUBLIC_API_BASE_URL);
    checks.api_https_and_prefix = publicOrigin(api.origin) && api.pathname === '/api/v1' && !api.search && !api.hash
      && !api.username && !api.password;
  } catch { checks.api_https_and_prefix = false; }
  checks.server_api_matches_browser = !env.INTERNAL_API_BASE_URL || env.INTERNAL_API_BASE_URL === env.NEXT_PUBLIC_API_BASE_URL;
  return { status: Object.values(checks).every(Boolean) ? 'configuration_passed' : 'blocked', checks, ready_for_public_users: false };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = checkDeployment(process.env);
  console.log(JSON.stringify(result));
  process.exitCode = result.status === 'configuration_passed' ? 0 : 2;
}
