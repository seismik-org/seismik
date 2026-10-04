import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import worker from '../deploy/cloudflare-edge-router.js';
import { FALLBACK_ASSETS } from '../deploy/fallback-assets.js';

const request = (path = '/', host = 'seismik.org', method = 'GET') => new Request(`https://${host}${path}`, { method, headers: { Accept: 'text/html' } });
test('edge survives a failed origin, preserving 503 and serving its own assets', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('origin down'); };
  try {
    const response = await worker.fetch(request('/contact/'), {});
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('Retry-After'), '60');
    assert.match(await response.text(), /Tu seguridad no espera/);
    for (const path of Object.keys(FALLBACK_ASSETS)) {
      const asset = await worker.fetch(request(path), {});
      assert.equal(asset.status, 200);
      assert.ok((await asset.text()).length);
    }
    const api = await worker.fetch(request('/v1/events', 'api.seismik.org'), {});
    assert.equal(api.status, 503);
    assert.match(api.headers.get('Content-Type'), /json/);
    assert.deepEqual(await api.json(), { detail: 'Service temporarily unavailable' });
    const auth = await worker.fetch(request('/login', 'auth.seismik.org'), {});
    assert.match(auth.headers.get('Content-Type'), /json/);
    const head = await worker.fetch(request('/', 'seismik.org', 'HEAD'), {});
    assert.equal(await head.text(), '');
  } finally { globalThis.fetch = original; }
});
test('5xx pages get fallback; 404, healthy responses and API payloads survive', async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [200, 404, 500, 502, 503, 504]) {
      globalThis.fetch = async () => new Response('upstream', { status });
      const response = await worker.fetch(request(), {});
      assert.equal(response.status, status >= 500 ? 503 : status);
      assert.equal((await response.text()).includes('Tu seguridad'), status >= 500);
      const api = await worker.fetch(request('/v1/events', 'api.seismik.org'), {});
      assert.equal(api.status, status);
      assert.equal(await api.text(), 'upstream');
    }
  } finally { globalThis.fetch = original; }
});

test('service worker provides cached navigation and assets without caching private data', async () => {
  const handlers = {};
  const stored = new Map();
  const cache = { put: async (key, value) => stored.set(key, value), };
  const context = {
    self: { location: { origin: 'https://seismik.org' }, addEventListener: (name, handler) => handlers[name] = handler, skipWaiting: async () => {}, clients: { claim: async () => {} } },
    caches: { open: async () => cache, match: async (key) => stored.get(key)?.clone(), keys: async () => [], delete: async () => true },
    fetch: async (path) => new Response(FALLBACK_ASSETS[path]), Response, Headers, URL, AbortSignal,
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/sw.js', 'utf8'), context);
  let pending;
  handlers.install({ waitUntil: (p) => pending = p });
  await pending;
  assert.deepEqual([...stored.keys()], ['/offline.html', '/offline.css', '/offline.js', '/site.js']);
  context.fetch = async () => { throw new Error('offline'); };
  const navigate = (path, mode = 'navigate') => {
    let response;
    handlers.fetch({ request: { url: `https://seismik.org${path}`, method: 'GET', mode }, respondWith: (p) => response = p });
    return response;
  };
  assert.match(await (await navigate('/contact/')).text(), /Tu seguridad/);
  assert.match(await (await navigate('/offline.css?v=example', 'cors')).text(), /color-scheme/);
  for (const path of ['/v1/events', '/api/status', '/login', '/id/session', '/__/auth/callback']) assert.equal(navigate(path), undefined);
  context.fetch = async () => new Response('not found', { status: 404 });
  assert.equal((await navigate('/missing')).status, 404);
  context.fetch = async () => new Response('down', { status: 503 });
  assert.match(await (await navigate('/')).text(), /Tu seguridad/);
});

test('both router entry points and embedded fallback stay synchronized', () => {
  assert.equal(readFileSync('edge-worker/worker.js', 'utf8'), readFileSync('deploy/cloudflare-edge-router.js', 'utf8'));
  for (const [path, contents] of Object.entries(FALLBACK_ASSETS)) {
    assert.equal(contents.replace(/\?v=[a-f0-9]{16}/g, '?v=__ASSET_VERSION__'), readFileSync(`web${path}`, 'utf8'));
  }
});
