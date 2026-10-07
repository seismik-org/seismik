import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { randomUUID } from 'node:crypto';
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

test('felt host routes to web and API and replaces spoofed visitor identity', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (req) => { calls.push(req); return new Response('ok'); };
  try {
    const host = 'ifeltit.seismik.org';
    const page = await worker.fetch(new Request(`https://${host}/`, {headers: {
      'X-Seismik-Origin-Auth': 'spoof', 'X-Seismik-Client-IP': 'spoof',
    }}), { EDGE_ORIGIN_SECRET: 'edge-secret' });
    assert.match(calls[0].url, /seismik-web-.*\/ifeltit.html$/);
    assert.equal(calls[0].headers.get('X-Seismik-Origin-Auth'), null);
    assert.equal(calls[0].headers.get('X-Seismik-Client-IP'), null);
    assert.match(page.headers.get('Permissions-Policy'), /geolocation=\(self\)/);
    assert.match(page.headers.get('Content-Security-Policy'), /frame-src https:\/\/challenges.cloudflare.com/);
    const body = JSON.stringify({report_id:'test-report'});
    await worker.fetch(new Request(`https://${host}/v1/reports/web/felt`, {
      method:'POST', body, headers:{'X-Seismik-Client-IP':'spoof','CF-Connecting-IP':'1.2.3.4'},
    }), {EDGE_ORIGIN_SECRET:'edge-secret'});
    assert.match(calls[1].url, /seismik-api-.*\/v1\/reports\/web\/felt$/);
    assert.equal(calls[1].headers.get('X-Seismik-Client-IP'),'1.2.3.4');
    assert.equal(calls[1].headers.get('X-Seismik-Origin-Auth'),'edge-secret');
    assert.equal(await calls[1].text(),body);
    const home = await worker.fetch(request(),{});
    assert.match(home.headers.get('Permissions-Policy'), /geolocation=\(\)/);
  } finally { globalThis.fetch = original; }
});

test('browser keeps its ID across failures, rotates on edits and confirms only accepted responses', async () => {
  const node = () => ({
    hidden: false, disabled: false, textContent: '', value: '', checked: false,
    listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; },
    checkValidity: () => true, reportValidity() {}, replaceChildren() {}, append() {},
    setAttribute() {}, removeAttribute() {},
  });
  const values = {
    felt: 'true', intensity_mmi: '4', country_code: 'CO', latitude: '4.651234',
    longitude: '-74.051234', observed_at: '', duration_seconds: '15', building_height: '', floor: '',
    movement: 'rolling', activity: '', building_type: '', reaction: '', others_felt: '',
    noise: '', windows: '', lamps: '', furniture: '', precise: '', share_with_official_agencies: '',
  };
  const controls = Object.fromEntries(Object.entries(values).map(([name,value]) => [name, {...node(),name,value}]));
  const fieldsets = Array.from({length:3}, () => ({...node(), querySelectorAll: () => Object.values(controls)}));
  const buttons = Array.from({length:4},node);
  const form = {...node(), elements: {namedItem: name => controls[name]},
    querySelectorAll: selector => selector === '[data-step]' ? fieldsets : buttons};
  const nodes = {'#report-form':form};
  const document = {
    querySelector: selector => nodes[selector] ||= node(),
    querySelectorAll: () => Array.from({length:3},node), createElement: node,
  };
  let mode = 'offline';
  const posts = [];
  const context = {
    document, window:{location:{reload(){}}}, navigator:{}, Date, URL, AbortSignal,
    crypto:{randomUUID},
    FormData: class { get(name) { return controls[name].value; } },
    fetch: async (url, init) => {
      if (url.endsWith('/config')) return {ok:true,json:async()=>({enabled:true,turnstile_required:false})};
      const report = JSON.parse(init.body); posts.push(report);
      if (mode === 'offline') throw new Error('Network unavailable');
      return {status:mode === 'wrong-status' ? 200 : 202, json:async()=>({
        report_id:mode === 'wrong-id' ? 'another-report' : report.report_id,
        accepted:mode === 'accepted', duplicate:mode === 'duplicate', agency_routes:[],notice:'Received',
      })};
    },
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/ifeltit.js','utf8'),context);
  await new Promise(setImmediate);
  const submit = () => form.listeners.submit({preventDefault(){}});
  await submit(); await submit();
  assert.equal(posts[0].report_id,posts[1].report_id);
  assert.equal(controls.duration_seconds.value,'15');
  assert.ok(fieldsets.every(el=>!el.disabled));
  assert.equal(form.hidden,false);
  for (mode of ['not-accepted','wrong-status','wrong-id']) {
    await submit(); assert.equal(form.hidden,false);
    assert.equal(posts.at(-1).report_id,posts[0].report_id);
  }
  controls.duration_seconds.value = '20';
  form.listeners.input({target:controls.duration_seconds});
  mode = 'duplicate'; await submit();
  assert.notEqual(posts.at(-1).report_id,posts[0].report_id);
  assert.equal(posts.at(-1).duration_seconds,20);
  assert.equal(form.hidden,true);
  assert.equal(nodes['#result'].hidden,false);
});
