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
    Intl, Date, Error, setTimeout, clearTimeout, ...globals });
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
      useRef(initial) { const i = index++; if (!(i in values)) values[i] = { current: initial }; return values[i]; },
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

function actionHarness(api) {
  const h = hooks(), timers = [], refreshed = [];
  const { VideoActions } = load('components/video-actions.tsx', {
    react: h.react, 'react/jsx-runtime': jsx,
    'next/navigation': { useRouter: () => ({ refresh: () => refreshed.push(true) }) },
    'next/link': { default: 'a' },
    '@/lib/language': { useTranslator: () => value => value },
    '@/components/ui': { Button: 'button', SecondaryButton: 'button' },
    '@/lib/api': api,
    '@/lib/utils': { videoStageLabel: video => video.status },
  }, { setTimeout: (callback, delay) => { assert.equal(delay, 3000); timers.push(callback); return callback; },
    clearTimeout: callback => { const i = timers.indexOf(callback); if (i >= 0) timers.splice(i, 1); } });
  return { ...h, timers, refreshed, render(video) { h.reset(); return VideoActions({ video }); } };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const syntheticVideo = { id: 'synthetic-video', status: 'completed', transcript: null, summary: null, processing_error: null };

test('enqueue immediately locks actions while server props still show the old terminal state', async () => {
  const h = actionHarness({ runVideo: async () => ({ status: 'queued', message: 'accepted' }) });
  const tree = h.render(syntheticVideo);
  await nodes(tree).find(node => node.type === 'button').props.onClick();
  const queued = h.render(syntheticVideo);
  assert.match(text(queued), /queued/);
  assert.equal(nodes(queued).find(node => node.type === 'button').props.disabled, true);
});

test('queued through processing to persisted notes refreshes details automatically and stops', async () => {
  let stage = 0, videoReads = 0, taskReads = 0;
  const states = ['queued', 'transcribing', 'analyzing', 'embedding', 'completed'];
  const h = actionHarness({
    getVideo: async () => { videoReads++; return { ...syntheticVideo, status: states[stage],
      summary: stage === 4 ? { markdown_note: 'Persisted synthetic notes' } : null }; },
    getVideoTask: async () => { taskReads++; return { status: stage === 4 ? 'succeeded' : stage === 0 ? 'queued' : 'running', stage: states[stage] }; },
  });
  const initial = { ...syntheticVideo, status: 'queued' };
  h.render(initial);
  h.effects[0]();
  for (stage = 0; stage < states.length; stage++) {
    if (stage) h.timers.shift()();
    await tick();
    const tree = h.render(initial);
    assert.match(text(tree), new RegExp(states[stage]));
    assert.equal(nodes(tree).find(node => node.type === 'button').props.disabled, stage < 4);
    assert.equal(h.timers.length, stage < 4 ? 1 : 0);
    assert.equal(h.refreshed.length, stage < 4 ? 0 : 1);
  }
  assert.equal(videoReads, 5);
  assert.equal(taskReads, 5);
  assert.equal(h.values[4].summary.markdown_note, 'Persisted synthetic notes');
});

test('running task keeps stale completed video locked until both reads reach terminal state', async () => {
  const h = actionHarness({ getVideo: async () => syntheticVideo,
    getVideoTask: async () => ({ status: 'running', stage: 'embedding' }) });
  h.render(syntheticVideo);
  h.effects[0]();
  await tick();
  assert.equal(nodes(h.render(syntheticVideo)).find(node => node.type === 'button').props.disabled, true);
  assert.equal(h.refreshed.length, 0);
  assert.equal(h.timers.length, 1);
});

test('transient read failure retries, and unmount ignores an in-flight result', async () => {
  let resolveVideo, calls = 0;
  const h = actionHarness({
    getVideo: () => { if (++calls === 1) return Promise.reject(new Error('temporary')); return new Promise(resolve => { resolveVideo = resolve; }); },
    getVideoTask: async () => ({ status: 'succeeded', stage: 'completed' }),
  });
  h.render({ ...syntheticVideo, status: 'processing' });
  const cleanup = h.effects[0]();
  await tick();
  assert.equal(h.timers.length, 1);
  h.timers.shift()();
  await tick();
  assert.equal(h.timers.length, 0); // No overlapping poll while the read is pending.
  cleanup();
  resolveVideo(syntheticVideo);
  await tick();
  assert.equal(h.refreshed.length, 0);
  assert.equal(h.timers.length, 0);
  assert.equal(h.values[4], null);
});

test('chat renders returned citations as owner detail links and sends the chosen language once', async () => {
  const h = hooks(), calls = [];
  const source = { video_id: 'synthetic-owner-video', title: 'Synthetic source', snippet: 'Evidence from the saved transcript', category: 'Test', distance: 0.1 };
  const { ChatClient } = load('components/chat-client.tsx', {
    react: h.react, 'react/jsx-runtime': jsx,
    '@/lib/language': { useTranslator: () => value => value, useLanguage: () => ({ language: 'zh' }) },
    '@/components/ui': { Button: 'button', SecondaryButton: 'button', Panel: 'section', Textarea: 'textarea' },
    '@/lib/api': { chatWithVideos: async payload => { calls.push(payload); return { answer: 'Synthetic grounded answer', sources: [source] }; } },
    '@/lib/chat-citations': load('lib/chat-citations.ts'),
  });
  nodes(ChatClient()).find(node => node.type === 'textarea').props.onChange({ target: { value: 'Synthetic question' } });
  h.reset();
  await nodes(ChatClient()).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
  h.reset();
  const tree = ChatClient();
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [{ question: 'Synthetic question', limit: 5, language: 'zh' }]);
  assert.match(text(tree), /Synthetic grounded answer/);
  assert.match(text(tree), /Evidence from the saved transcript/);
  const link = nodes(tree).find(node => node.type === 'a');
  assert.equal(link.props.href, '/videos/synthetic-owner-video');
  assert.match(text(link), /\[1\]\s+Synthetic source/);
});

test('numbered references preserve text and link only this response\'s available sources', () => {
  const { splitAnswerCitations } = load('lib/chat-citations.ts');
  for (const [answer, count, expected] of [
    ['One[1][2], again[1]. Unknown[3][0][01][99999999999999999999999]', 2, '0,1,0'],
    ['No evidence [1]', 0, ''],
    ['Visible[1] `array[1]` [2]\n```js\n[2]\n````\n[1]', 2, '0,1,0'],
    ['~~~text\n[1]\n~~~\n[2]', 2, '1'],
    ['``code`[1]`` [2]', 2, '1'],
    ['Unclosed `[1] and [2]', 2, ''],
    [String.raw`Escaped \[1], actual \\[2]`, 2, '1'],
    ['[1](https://example.com/(path[2])) plain[2]', 2, '1'],
    ['[1](https://example.com/unclosed[2]', 2, ''],
  ]) {
    const parts = splitAnswerCitations(answer, count);
    assert.equal(parts.map(part => part.text).join(''), answer);
    assert.equal(parts.filter(part => part.sourceIndex !== undefined).map(part => part.sourceIndex).join(','), expected);
  }
});

test('inline citations navigate to matching owner videos and update with the next answer', async () => {
  const h = hooks();
  const first = { video_id: 'owner-a', title: 'Evidence A', snippet: 'Passage A', category: null, distance: null };
  const second = { ...first, video_id: 'owner-b', title: 'Evidence B' };
  const results = [
    { answer: 'Claims[2][1][2]. Unknown[9]. Code `[1]`. [1](https://example.com/foreign)', sources: [first, second] },
    { answer: 'New answer[1][2]', sources: [second] },
  ];
  const { ChatClient } = load('components/chat-client.tsx', {
    react: h.react, 'react/jsx-runtime': jsx,
    '@/lib/language': { useTranslator: () => value => value, useLanguage: () => ({ language: 'zh' }) },
    '@/components/ui': { Button: 'button', SecondaryButton: 'button', Panel: 'section', Textarea: 'textarea' },
    '@/lib/chat-citations': load('lib/chat-citations.ts'),
    '@/lib/api': { chatWithVideos: async () => results.shift() },
  });
  async function submit() {
    h.reset();
    nodes(ChatClient()).find(node => node.type === 'textarea').props.onChange({ target: { value: 'Synthetic question' } });
    h.reset();
    await nodes(ChatClient()).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} });
    h.reset();
    return ChatClient();
  }
  let tree = await submit();
  let citations = nodes(tree).filter(node => node.type === 'a' && node.props['aria-label']);
  assert.equal(citations.map(node => node.props.href).join(','), '/videos/owner-b,/videos/owner-a,/videos/owner-b');
  assert.equal(citations[0].props.title, 'Evidence B');
  assert.equal(citations[0].props['aria-label'], '[2] Evidence B');
  assert.match(text(tree), /Unknown\[9\]/);
  assert.ok(nodes(tree).filter(node => node.type === 'a').every(node => node.props.href.startsWith('/videos/')));
  tree = await submit();
  citations = nodes(tree).filter(node => node.type === 'a' && node.props['aria-label']);
  assert.equal(citations.length, 1);
  assert.equal(citations[0].props.href, '/videos/owner-b');
  assert.match(text(tree), /\[2\]/); // Missing source never reuses the preceding answer's source.
});

function chatHarness(api) {
  const h = hooks();
  const { ChatClient } = load('components/chat-client.tsx', {
    react: h.react, 'react/jsx-runtime': jsx,
    '@/lib/language': { useTranslator: () => value => value, useLanguage: () => ({ language: 'zh' }) },
    '@/components/ui': { Button: 'button', SecondaryButton: 'button', Panel: 'section', Textarea: 'textarea' },
    '@/lib/chat-citations': load('lib/chat-citations.ts'),
    '@/lib/api': { chatWithVideos: api },
  });
  const render = () => { h.reset(); return ChatClient(); };
  return { ...h, render,
    change(value) { nodes(render()).find(node => node.type === 'textarea').props.onChange({ target: { value } }); },
    submit() { return nodes(render()).find(node => node.type === 'form').props.onSubmit({ preventDefault() {} }); },
  };
}

test('same-render duplicate submits send one request and response stays tied to the submitted question', async () => {
  const calls = [];
  let complete;
  const h = chatHarness(payload => { calls.push(payload); return new Promise(resolve => { complete = resolve; }); });
  h.change('  Original question\n');
  const submit = nodes(h.render()).find(node => node.type === 'form').props.onSubmit;
  const first = submit({ preventDefault() {} });
  await submit({ preventDefault() {} }); // Same render, before loading state can disable anything.
  assert.equal(calls.length, 1);
  assert.equal(nodes(h.render()).find(node => node.props?.type === 'submit').props.disabled, true);
  h.change('Draft follow-up');
  nodes(h.render()).find(node => node.props?.type === 'range').props.onChange({ target: { value: '2' } });
  await h.submit(); // Re-rendering must not release the request guard.
  assert.equal(calls.length, 1);
  assert.equal(calls[0].question, 'Original question');
  assert.equal(calls[0].limit, 5);
  complete({ answer: 'Synthetic answer', sources: [] });
  await first;
  const tree = h.render();
  assert.match(text(tree), /回答的问题.*Original question/);
  assert.equal(nodes(tree).find(node => node.type === 'textarea').props.value, 'Draft follow-up');
  assert.equal(nodes(tree).find(node => node.props?.type === 'submit').props.disabled, false);
});

test('failed chat releases the guard for an explicit retry and clears its error after success', async () => {
  let calls = 0;
  const h = chatHarness(async () => {
    if (++calls === 1) throw new Error('Synthetic unavailable');
    return { answer: 'Recovered answer', sources: [] };
  });
  h.change('Synthetic question');
  await h.submit();
  assert.match(text(h.render()), /Synthetic unavailable/);
  await h.submit();
  assert.equal(calls, 2);
  assert.doesNotMatch(text(h.render()), /Synthetic unavailable/);
  assert.match(text(h.render()), /Recovered answer/);
});

for (const failure of [false, true]) {
  test(`unmounted chat ignores late ${failure ? 'failure' : 'success'} and does not submit again`, async () => {
    let finish, calls = 0;
    const h = chatHarness(() => { calls++; return new Promise((resolve, reject) => {
      finish = () => failure ? reject(new Error('Late failure')) : resolve({ answer: 'Late answer', sources: [] });
    }); });
    h.change('Synthetic question');
    const unmount = h.effects[0]();
    const request = h.submit();
    unmount();
    const before = JSON.stringify(h.values.slice(0, 5));
    finish();
    await request;
    assert.equal(JSON.stringify(h.values.slice(0, 5)), before);
    await h.submit();
    assert.equal(calls, 1);
  });
}

test('whitespace-only chat does not reach the API even when submitted directly', async () => {
  let calls = 0;
  const h = chatHarness(async () => { calls++; return { answer: 'Unexpected', sources: [] }; });
  h.change(' \n\t ');
  await h.submit();
  assert.equal(calls, 0);
  assert.equal(nodes(h.render()).find(node => node.props?.type === 'submit').props.disabled, true);
});
