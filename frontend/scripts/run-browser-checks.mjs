import { spawn } from 'node:child_process';
import { cp, mkdtemp, mkdir, readdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { browserEnvironment, copyBrowserSource } from './browser-sandbox.mjs';

const source = await realpath(fileURLToPath(new URL('..', import.meta.url)));
const sandbox = await mkdtemp(path.join(tmpdir(), 'videomind-browser-'));
if ((await realpath(sandbox)).startsWith(source + path.sep)) {
  await rm(sandbox, { recursive: true, force: true });
  throw new Error('Browser temporary directory must be outside the frontend source');
}
let artifacts = await mkdtemp(path.join(tmpdir(), 'videomind-browser-report-'));
if (process.env.VIDEOMIND_BROWSER_ARTIFACT_DIR) {
  const parent = path.resolve(process.env.VIDEOMIND_BROWSER_ARTIFACT_DIR);
  await mkdir(parent, { recursive: true });
  artifacts = await mkdtemp(path.join(parent, 'run-'));
}
const env = browserEnvironment(process.env, sandbox, artifacts);
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
let active, interrupted = false;
const stop = signal => { interrupted = true; active?.kill(signal); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
async function run(args, executable = npm) {
  if (interrupted) throw new Error('Browser checks interrupted');
  await new Promise((resolve, reject) => {
    active = spawn(executable, args, { cwd: sandbox, env, stdio: 'inherit' });
    active.once('error', reject);
    active.once('close', code => {
      active = undefined;
      if (code === 0 && !interrupted) resolve();
      else reject(new Error(`Browser check phase failed: ${args[0]} (${code})`));
    });
  });
}
try {
  await copyBrowserSource(source, sandbox);
  console.log(`Isolated browser workspace: ${sandbox}`);
  await run(['ci', '--no-audit', '--no-fund']);
  await run(['exec', '--no', '--', 'playwright', 'install', 'chromium', '--only-shell']);
  const unitFiles = (await readdir(path.join(sandbox, 'scripts')))
    .filter(name => name.endsWith('.test.mjs')).map(name => 'scripts/' + name);
  await run(['--test', ...unitFiles], process.execPath);
  await run(['run', 'build']);
  await run(['run', 'typecheck']);
  await run(['run', 'lint']);
  await cp(path.join(sandbox, '.next/static'), path.join(sandbox, '.next/standalone/.next/static'), { recursive: true });
  try {
    await cp(path.join(sandbox, 'public'), path.join(sandbox, '.next/standalone/public'), { recursive: true });
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await run(['exec', '--no', '--', 'playwright', 'test']);
  console.log(`Browser checks passed. Synthetic report: ${artifacts}`);
  await rm(sandbox, { recursive: true, force: true });
} catch (error) {
  console.error(error.message);
  console.error(`Isolated workspace retained for diagnosis: ${sandbox}`);
  process.exitCode = 1;
} finally {
  process.off('SIGINT', stop);
  process.off('SIGTERM', stop);
}
