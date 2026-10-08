import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { randomUUID } from 'node:crypto';
import worker from '../deploy/cloudflare-edge-router.js';
import { FALLBACK_ASSETS } from '../deploy/fallback-assets.js';

const request = (path = '/', host = 'seismik.org', method = 'GET') => new Request(`https://${host}${path}`, { method, headers: { Accept: 'text/html' } });
test('admin has strict headers and sends its API requests to the protected origin', async () => {
  const original = globalThis.fetch;
  const targets = [];
  const hostHeaders = [];
  globalThis.fetch = async (target) => {
    targets.push(target.url || String(target)); hostHeaders.push(target.headers.get('X-Seismik-Admin-Host'));
    return new Response('ok');
  };
  try {
    const page = await worker.fetch(request('/', 'admin.seismik.org'), {});
    assert.match(targets[0], /seismik-web.*\/admin\/$/);
    assert.equal(page.headers.get('Cache-Control'), 'no-store');
    assert.equal(page.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    assert.match(page.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
    await worker.fetch(request('/v1/admin/me', 'admin.seismik.org'), {});
    assert.match(targets[1], /seismik-api.*\/v1\/admin\/me$/);
    assert.equal(hostHeaders[1], 'admin.seismik.org');
    await worker.fetch(new Request('https://api.seismik.org/v1/admin/me', {
      headers: {'X-Seismik-Admin-Host': 'admin.seismik.org'},
    }), {});
    assert.equal(hostHeaders[2], null);
  } finally { globalThis.fetch = original; }
});

test('admin CSV neutralizes formulas in untrusted report fields', async () => {
  let blob;
  const context = {
    document: {
      querySelector: selector => ({value: selector === '#filter-q' ? '' : 'all', addEventListener() {}}),
      createElement: () => ({click() {}}),
    },
    Intl, Blob, setTimeout() {},
    URL: {createObjectURL: value => { blob = value; return 'blob:test'; }},
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/reportes.js', 'utf8'), context);
  for (const value of ['=HYPERLINK("https://evil.example")', '+cmd', '@SUM(1)', '-cmd', ' \t=1+1']) {
    context.example = value;
    vm.runInContext(`reports = [{received_at:'now',source:'web',kind:'felt',event:{place:example},report:{report_id:'safe',longitude:-74.05},plausibility:{status:'unknown',reasons:[]}}]; exportCsv();`, context);
    assert.ok((await blob.text()).includes(`"'${value.replaceAll('"', '""')}"`));
    assert.ok((await blob.text()).includes('"-74.05"'));
  }
});
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
  assert.deepEqual([...stored.keys()], ['/offline.html', '/offline.css', '/footer.css', '/offline.js', '/site.js']);
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
    assert.equal(contents.replace(/\?v=[a-f0-9]{16}/g, '?v=__ASSET_VERSION__').replace(/\r\n/g, '\n'), readFileSync(`web${path}`, 'utf8').replace(/\r\n/g, '\n'));
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
    setAttribute() {}, removeAttribute() {}, querySelector:()=>node(),
  });
  const values = {
    earthquake_event_id:'catalog:test:event-001', felt: 'true', intensity_mmi: '4', country_code: 'CO', latitude: '4.651234',
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
    querySelectorAll: () => Array.from({length:3},node), createElement: node, head:node(),
  };
  let mode = 'offline';
  const mapListeners = {};
  let mapCenter;
  const posts = [];
  const context = {
    document, window:{location:{reload(){}}, google:{maps:{
      Map:class {
        constructor(element,options) { mapCenter=options.center; }
        addListener(name,listener) { mapListeners[name]=listener; }
        panTo(point) { mapCenter=point; } setZoom() {}
        getCenter() { return {lat:()=>mapCenter.lat,lng:()=>mapCenter.lng}; }
      }, Circle:class { setCenter(point) { this.point=point; } },
      Marker:class { setPosition(point) { this.point=point; } addListener() {} }, SymbolPath:{CIRCLE:0},
    }}}, navigator:{}, Date, URL, URLSearchParams, AbortSignal, Intl,
    crypto:{randomUUID},
    FormData: class { get(name) { return controls[name].value; } },
    fetch: async (url, init) => {
      if (url.endsWith('/config')) return {ok:true,json:async()=>({enabled:true,turnstile_required:false,google_maps_api_key:'test-browser-key'})};
      if (url.endsWith('/events')) return {ok:true,json:async()=>({events:[{event_id:'catalog:test:event-001',origin_time:'2026-10-07T15:00:00Z',magnitude:3,place:'Colombia',latitude:1,longitude:2}]})};
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
  controls.latitude.value=''; controls.longitude.value='';
  context.window.initFeltMap();
  controls.earthquake_event_id.listeners.change();
  assert.equal(controls.latitude.value,'', 'Epicenter must not select the reporter location');
  await submit(); assert.equal(posts.length,0, 'Missing map location must prevent submission');
  mapListeners.click({latLng:{lat:()=>4.651234,lng:()=>-74.051234}});
  assert.equal(controls.latitude.value,4.651234);
  assert.equal(controls.longitude.value,-74.051234);
  await submit(); await submit();
  assert.equal(posts[0].earthquake_event_id,'catalog:test:event-001');
  assert.equal(posts[0].report_id,posts[1].report_id);
  assert.equal(controls.duration_seconds.value,'15');
  assert.ok(fieldsets.every(el=>!el.disabled));
  assert.equal(form.hidden,false);
  for (mode of ['not-accepted','wrong-status','wrong-id']) {
    await submit(); assert.equal(form.hidden,false);
    assert.equal(posts.at(-1).report_id,posts[0].report_id);
  }
  mapListeners.click({latLng:{lat:()=>4.7,lng:()=>-74.1}});
  mode='offline'; await submit(); await submit();
  assert.notEqual(posts.at(-1).report_id,posts[0].report_id,'Moving the map point creates a new identifier');
  assert.equal(posts.at(-1).report_id,posts.at(-2).report_id);
  assert.equal(posts.at(-1).latitude,4.7);
  controls.duration_seconds.value = '20';
  form.listeners.input({target:controls.duration_seconds});
  mode = 'duplicate'; await submit();
  assert.notEqual(posts.at(-1).report_id,posts[0].report_id);
  assert.equal(posts.at(-1).duration_seconds,20);
  assert.equal(form.hidden,true);
  assert.equal(nodes['#result'].hidden,false);
});


test('Maps permissions and fresh CSP nonces stay confined to the felt HTML host', async () => {
  const originalFetch=globalThis.fetch, originalRewriter=globalThis.HTMLRewriter;
  let forwarded;
  globalThis.fetch=async req => { forwarded=req; return new Response('<script src="/ifeltit.js"></script>',{
    headers:{'Content-Type':'text/html','ETag':'old'},
  }); };
  globalThis.HTMLRewriter=class {
    on(selector,handler) { this.handler=handler; return this; }
    async transform(response) {
      let nonce;
      this.handler.element({setAttribute(name,value) { assert.equal(name,'nonce'); nonce=value; }});
      return new Response((await response.text()).replace('<script ',`<script nonce="${nonce}" `),{headers:response.headers});
    }
  };
  try {
    const req=()=>new Request('https://ifeltit.seismik.org/',{headers:{'If-None-Match':'old'}});
    const first=await worker.fetch(req(),{}), second=await worker.fetch(req(),{});
    assert.equal(forwarded.headers.get('If-None-Match'),null);
    assert.equal(first.headers.get('Cache-Control'),'no-store');
    assert.equal(first.headers.get('ETag'),null);
    const firstNonce=(await first.text()).match(/nonce="([a-f0-9]{32})"/)[1];
    const secondNonce=(await second.text()).match(/nonce="([a-f0-9]{32})"/)[1];
    assert.notEqual(firstNonce,secondNonce);
    const csp=first.headers.get('Content-Security-Policy');
    assert.ok(csp.includes(`'nonce-${firstNonce}'`));
    assert.ok(csp.includes('https://maps.googleapis.com'));
    assert.equal(csp.includes("'unsafe-inline'"),false);
    assert.equal(first.headers.get('Referrer-Policy'),'strict-origin-when-cross-origin');
    const home=await worker.fetch(request(),{});
    assert.equal(home.headers.get('Content-Security-Policy').includes('googleapis.com'),false);
    assert.equal(home.headers.get('Referrer-Policy'),'no-referrer');
  } finally { globalThis.fetch=originalFetch; globalThis.HTMLRewriter=originalRewriter; }
});
