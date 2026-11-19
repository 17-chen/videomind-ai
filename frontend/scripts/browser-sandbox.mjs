import { cp, copyFile, lstat, mkdir } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import path from 'node:path';

export const origins = JSON.parse(readFileSync(new URL('../e2e/origins.json', import.meta.url), 'utf8'));
for (const origin of Object.values(origins)) {
  const url = new URL(origin);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || Number(url.port) < 40000 || url.origin !== origin) {
    throw new Error('Browser checks require isolated loopback test origins');
  }
}
if (origins.apiOrigin === origins.appOrigin) throw new Error('Browser test ports must differ');

export function browserEnvironment(source, sandbox, artifacts) {
  const keep = ['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'SystemRoot', 'TMPDIR', 'TEMP', 'TMP', 'CI',
    'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'npm_config_cache'];
  const env = Object.fromEntries(keep.filter(key => source[key] !== undefined).map(key => [key, source[key]]));
  return { ...env,
    NO_PROXY: '127.0.0.1,localhost', no_proxy: '127.0.0.1,localhost',
    NEXT_TELEMETRY_DISABLED: '1', NEXT_PUBLIC_API_BASE_URL: origins.apiOrigin + '/api/v1',
    INTERNAL_API_BASE_URL: origins.apiOrigin + '/api/v1',
    NEXT_PUBLIC_SUPABASE_URL: '', NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
    VIDEOMIND_BROWSER_ISOLATED: '1', VIDEOMIND_BROWSER_ARTIFACT_DIR: artifacts,
    PLAYWRIGHT_BROWSERS_PATH: source.PLAYWRIGHT_BROWSERS_PATH || path.join(sandbox, 'browsers'),
    PLAYWRIGHT_SKIP_BROWSER_GC: '1',
  };
}

export async function copyBrowserSource(source, sandbox) {
  const filter = async file => !['.next', 'node_modules'].includes(path.basename(file)) &&
    !path.basename(file).startsWith('.env') && !(await lstat(file)).isSymbolicLink();
  for (const name of ['app', 'components', 'lib', 'public', 'scripts', 'e2e']) {
    try {
      await cp(path.join(source, name), path.join(sandbox, name), { recursive: true, filter });
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  await mkdir(sandbox, { recursive: true });
  for (const name of ['package.json', 'package-lock.json', 'next-env.d.ts', 'next.config.ts', 'eslint.config.mjs',
    'postcss.config.js', 'tsconfig.json', 'tailwind.config.ts', 'proxy.ts', 'playwright.config.ts']) {
    await copyFile(path.join(source, name), path.join(sandbox, name));
  }
}
