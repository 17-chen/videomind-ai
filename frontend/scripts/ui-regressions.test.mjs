import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

const realRequire = createRequire(import.meta.url);
function load(file, mocks = {}, globals = {}) {
  const source = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: name => name in mocks ? mocks[name] : realRequire(name),
    Intl, Date, setTimeout, clearTimeout, ...globals });
  return exports;
}
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  return [node, ...[node.props?.children].flat(2).flatMap(nodes)];
}
function text(node) {
  if (typeof node === 'string') return node;
  if (!node || typeof node !== 'object') return '';
  return [node.props?.children].flat(2).map(text).join(' ');
}
function hooks() {
  const values = [], effects = [];
  let index = 0;
  return { values, effects, reset: () => { index = 0; },
    react: {
      useState(initial) { const i = index++; if (!(i in values)) values[i] = initial; return [values[i], value => { values[i] = value; }]; },
      useEffect(effect) { effects.push(effect); },
    },
  };
}

test('timestamps match across UTC and Shanghai hosts, including offsetless API values', () => {
  const { formatTimestamp } = load('lib/date.ts');
  const before = process.env.TZ;
  try {
    for (const language of ['zh', 'en']) {
      process.env.TZ = 'UTC';
      const server = formatTimestamp('2026-11-08T07:12:00Z', language);
      process.env.TZ = 'Asia/Shanghai';
      assert.equal(formatTimestamp('2026-11-08T07:12:00Z', language), server);
      assert.equal(formatTimestamp('2026-11-08T07:12:00', language), server);
      assert.equal(formatTimestamp('2026-11-08T15:12:00+08:00', language), server);
      assert.match(server, /15:12|03:12/);
    }
    assert.equal(formatTimestamp('invalid', 'zh'), null);
  } finally { if (before === undefined) delete process.env.TZ; else process.env.TZ = before; }
});

test('successful login starts a fresh document navigation; failed or missing session never enters', async () => {
  for (const result of [
    { data: { session: { access_token: 'synthetic' } }, error: null },
    { data: { session: null }, error: { message: 'invalid login' } },
    { data: { session: null }, error: null },
  ]) {
    const h = hooks(), destinations = [];
    const { AuthForm } = load('components/auth-form.tsx', {
      react: h.react, 'react/jsx-runtime': jsx,
      '@/lib/language': { useTranslator: () => value => value },
      '@/components/ui': { Button: 'button', Input: 'input' },
      '@/lib/supabase/config': { isSupabaseConfigured: true },
      '@/lib/supabase/client': { getSupabaseBrowserClient: () => ({ auth: { signInWithPassword: async () => result } }) },
    }, { window: { location: { replace: url => destinations.push(url) } } });
    const form = nodes(AuthForm()).find(node => node.type === 'form');
    await form.props.onSubmit({ preventDefault() {} });
    assert.deepEqual(destinations, result.data.session ? ['/dashboard'] : []);
    if (!result.data.session) assert.ok(h.values[5]);
  }
});

test('completed owner video unlocks stale processing UI and stops polling', async () => {
  const h = hooks(), timers = [], refreshed = [];
  const old = { id: 'synthetic-video', status: 'processing', transcript: null, summary: null, processing_error: null };
  const latest = { ...old, status: 'completed', transcript: { content: 'synthetic' } };
  const task = { status: 'succeeded', stage: 'completed', attempts: 1, error: null };
  const { VideoActions } = load('components/video-actions.tsx', {
    react: h.react, 'react/jsx-runtime': jsx,
    'next/navigation': { useRouter: () => ({ refresh: () => refreshed.push(true) }) },
    'next/link': { default: 'a' },
    '@/lib/language': { useTranslator: () => value => value },
    '@/components/ui': { Button: 'button', SecondaryButton: 'button' },
    '@/lib/api': { getVideo: async () => latest, getVideoTask: async () => task },
    '@/lib/utils': { videoStageLabel: video => video.status },
  }, { setTimeout: (...args) => timers.push(args), clearTimeout() {} });
  VideoActions({ video: old });
  h.effects[0]();
  await new Promise(resolve => setImmediate(resolve));
  h.reset();
  const tree = VideoActions({ video: old });
  assert.match(text(tree), /completed/);
  assert.doesNotMatch(text(tree), /处理中，请稍候/);
  assert.equal(nodes(tree).find(node => node.type === 'button').props.disabled, false);
  assert.equal(timers.length, 0);
  assert.equal(refreshed.length, 1);
});
