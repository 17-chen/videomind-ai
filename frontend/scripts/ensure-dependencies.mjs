// Docker development startup: keep a persisted dependency volume tied to its lockfile.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const marker = 'node_modules/.videomind-lock.sha256';
const lockText = readFileSync('package-lock.json', 'utf8');
const fingerprint = createHash('sha256').update(lockText).digest('hex');
const lock = JSON.parse(lockText);
const manifest = JSON.parse(readFileSync('package.json', 'utf8'));

function isCurrent() {
  try {
    if (readFileSync(marker, 'utf8').trim() !== fingerprint) return false;
    for (const section of ['dependencies', 'devDependencies', 'optionalDependencies']) {
      const requested = manifest[section] ?? {};
      const locked = lock.packages['']?.[section] ?? {};
      if (Object.keys(requested).length !== Object.keys(locked).length
        || Object.entries(requested).some(([name, spec]) => locked[name] !== spec)) return false;
    }
    const direct = { ...manifest.dependencies, ...manifest.devDependencies };
    return Object.keys(direct).every((name) => {
      const installed = JSON.parse(readFileSync(`node_modules/${name}/package.json`, 'utf8'));
      return installed.version === lock.packages[`node_modules/${name}`]?.version;
    });
  } catch {
    return false;
  }
}

if (!isCurrent()) {
  console.log('Synchronizing development dependencies with package-lock.json...');
  const install = spawnSync('npm', ['ci', '--no-audit', '--no-fund'], { stdio: 'inherit' });
  if (install.error || install.status !== 0) {
    console.error('Dependency synchronization failed; development server was not started.');
    process.exit(1);
  }
  writeFileSync(marker, `${fingerprint}\n`);
  if (!isCurrent()) {
    console.error('Installed dependency versions do not match the lockfile.');
    process.exit(1);
  }
}
console.log('Development dependencies match package-lock.json.');
