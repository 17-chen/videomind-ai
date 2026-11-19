import { createServer } from 'node:http';
import { origins } from '../scripts/browser-sandbox.mjs';

if (process.env.VIDEOMIND_BROWSER_ISOLATED !== '1') throw new Error('Synthetic API requires the isolated browser runner');
const timestamp = '2026-01-01T00:00:00Z';
const id = 'browser-video';
let mode, startedAt, task, video, metrics;
function reset(nextMode) {
  if (!['success', 'fail-once'].includes(nextMode)) throw new Error('Unknown synthetic scenario');
  mode = nextMode;
  startedAt = null;
  task = null;
  metrics = { runCalls: 0, cancelCalls: 0, chatCalls: 0, taskReads: 0, credentialAttempts: 0, observedStatuses: [] };
  video = { id, user_id: 'synthetic-owner', url: 'https://example.invalid/synthetic',
    title: 'Synthetic browser video', description: 'Synthetic browser fixture only',
    user_category: null, index_sync_error: null, duration: 12, thumbnail: null,
    status: 'created', source: 'upload', tags: [], processing_error: null,
    media_path: null, audio_path: null, processed_at: null, transcript: null, summary: null,
    created_at: timestamp, updated_at: timestamp };
}
reset('success');
function advance() {
  if (startedAt === null || task?.status === 'cancelled' || task?.status === 'failed' || task?.status === 'succeeded') return;
  const elapsed = Date.now() - startedAt;
  if (elapsed < 5000) {
    video.status = elapsed < 1000 ? 'queued' : elapsed < 2000 ? 'transcribing' : elapsed < 4000 ? 'analyzing' : 'embedding';
    task.status = video.status === 'queued' ? 'queued' : 'running';
    task.stage = video.status === 'transcribing' ? 'transcription' : video.status === 'analyzing' ? 'analysis' : video.status;
    return;
  }
  task.finished_at = timestamp;
  if (mode === 'fail-once' && metrics.runCalls === 1) {
    task.status = task.stage = video.status = 'failed';
    task.error = video.processing_error = 'Synthetic background failure';
    return;
  }
  video.status = task.stage = 'completed';
  task.status = 'succeeded';
  video.processed_at = timestamp;
  video.transcript = { id: 'synthetic-transcript', content: 'Synthetic saved transcript', created_at: timestamp, updated_at: timestamp };
  video.summary = { id: 'synthetic-summary', title: video.title, summary: 'Synthetic summary',
    key_points: ['Synthetic key point'], keywords: [], category: 'Synthetic', important_quotes: [],
    timeline: [], action_items: [], difficulty_level: null, target_audience: null, analysis_json: {},
    markdown_note: '# Synthetic note\n\nSynthetic persisted notes appeared automatically.', note_is_manual: false,
    created_at: timestamp, updated_at: timestamp };
}
async function body(req) {
  let input = '';
  for await (const chunk of req) {
    input += chunk;
    if (input.length > 16384) throw new Error('Synthetic request too large');
  }
  return JSON.parse(input || '{}');
}
function reply(res, status, value) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': origins.appOrigin,
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' });
  res.end(JSON.stringify(value));
}
const server = createServer(async (req, res) => {
  try {
    if (req.headers.authorization || req.headers['proxy-authorization']) {
      metrics.credentialAttempts++;
      return reply(res, 403, { detail: 'Credentials are not accepted by the synthetic API' });
    }
    if (req.headers.origin && req.headers.origin !== origins.appOrigin) return reply(res, 403, {});
    if (req.method === 'OPTIONS') return reply(res, 200, {});
    const pathname = new URL(req.url, origins.apiOrigin).pathname;
    if (pathname === '/__e2e/ready') return reply(res, 200, { synthetic: true });
    if (pathname === '/__e2e/reset' && req.method === 'POST') {
      reset((await body(req)).mode);
      return reply(res, 200, { synthetic: true });
    }
    advance();
    if (!metrics.observedStatuses.includes(video.status)) metrics.observedStatuses.push(video.status);
    if (pathname === '/__e2e/metrics') return reply(res, 200, metrics);
    if (pathname === `/api/v1/videos/${id}/run` && req.method === 'POST') {
      if (task?.status === 'queued' || task?.status === 'running') return reply(res, 409, { detail: 'Synthetic task already active' });
      metrics.runCalls++;
      startedAt = Date.now();
      video.status = 'queued';
      video.processing_error = null;
      task = { id: `synthetic-task-${metrics.runCalls}`, video_id: id, kind: 'run', status: 'queued', stage: 'queued',
        attempts: 1, error: null, cancel_requested_at: null, created_at: timestamp, started_at: null, finished_at: null };
      return reply(res, 202, { id, task_id: task.id, status: 'queued', message: 'Synthetic task queued' });
    }
    if (pathname === `/api/v1/videos/${id}/task/cancel` && req.method === 'POST') {
      if (!task || !['queued', 'running'].includes(task.status)) return reply(res, 409, {});
      metrics.cancelCalls++;
      task.status = task.stage = video.status = 'cancelled';
      task.cancel_requested_at = task.finished_at = timestamp;
      return reply(res, 200, task);
    }
    if (pathname === `/api/v1/videos/${id}/task`) { metrics.taskReads++; return reply(res, 200, task); }
    if (pathname === `/api/v1/videos/${id}`) return reply(res, 200, video);
    if (pathname === '/api/v1/videos/categories') return reply(res, 200, []);
    if (pathname === '/api/v1/videos') return reply(res, 200, { items: [video], total: 1, limit: 24, offset: 0 });
    if (pathname === '/api/v1/settings/ai') return reply(res, 200, {
      provider: null, model: null, has_api_key: false, has_asr_api_key: false, demo_mode: true, asr_provider: 'disabled',
    });
    if (pathname === '/api/v1/chat' && req.method === 'POST') {
      if ((await body(req)).question !== 'Synthetic browser question') return reply(res, 400, { detail: 'Only the fixed synthetic question is accepted' });
      metrics.chatCalls++;
      setTimeout(() => reply(res, 200, { answer: 'Synthetic evidence [1]. Unknown [99].', sources: [{
        video_id: id, title: video.title, url: 'https://example.invalid/not-a-navigation-target',
        category: 'Synthetic', distance: 0.1, snippet: 'Synthetic saved transcript',
      }] }), 800);
      return;
    }
    return reply(res, 404, { detail: 'Unknown synthetic route' });
  } catch {
    return reply(res, 400, { detail: 'Invalid synthetic request' });
  }
});
server.listen(Number(new URL(origins.apiOrigin).port), '127.0.0.1');
process.on('SIGTERM', () => server.close(() => process.exit(0)));
