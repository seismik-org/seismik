import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../deploy/cloudflare-edge-router.js';

test('LiveAhora routes home, policies and discovery while preserving shared assets and other hosts', async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async request => {
    requests.push(request);
    return new Response('<html></html>', {headers: {'Content-Type': 'text/html'}});
  };
  try {
    const paths = new Map([
      ['/', '/liveahora/'], ['/politicas', '/liveahora/politicas/'],
      ['/politicas/', '/liveahora/politicas/'], ['/robots.txt', '/liveahora/robots.txt'],
      ['/sitemap.xml', '/liveahora/sitemap.xml'], ['/styles.css', '/styles.css'],
      ['/assets/liveahora/logo.webp', '/assets/liveahora/logo.webp'],
      ['/liveahora/politicas/', '/liveahora/politicas/'], ['/v1/private', '/v1/private'],
      ['/admin', '/liveahora/admin/'], ['/admin/', '/liveahora/admin/'],
    ]);
    for (const [path, target] of paths) {
      const response = await worker.fetch(new Request(`https://liveahora.seismik.org${path}?test=1`, {
        headers: {'X-Seismik-Origin-Auth': 'untrusted'},
      }), {EDGE_ORIGIN_SECRET: 'test-only'});
      const request = requests.at(-1);
      assert.equal(new URL(request.url).pathname, target);
      assert.equal(new URL(request.url).search, '?test=1');
      assert.match(request.url, /^https:\/\/seismik-web-/);
      assert.equal(request.headers.get('X-Seismik-Origin-Auth'), null);
      assert.equal(response.status, 200);
      assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
      assert.match(response.headers.get('Content-Security-Policy'), /frame-src https:\/\/www.youtube-nocookie.com;/);
    }
    for (const path of ['/v1/liveahora/events', '/v1/liveahora/admin/events', '/v1/liveahora/login']) {
      const response = await worker.fetch(new Request(`https://liveahora.seismik.org${path}`, {headers:{'X-Seismik-Origin-Auth':'spoofed'}}), {EDGE_ORIGIN_SECRET:'test-only'});
      assert.match(requests.at(-1).url, /^https:\/\/seismik-api-/);
      assert.equal(new URL(requests.at(-1).url).pathname, path);
      assert.equal(requests.at(-1).headers.get('X-Seismik-Origin-Auth'), 'test-only');
      assert.equal(response.headers.get('Cache-Control'), 'no-store');
    }
    for (const [host, path] of [['seismik.org', '/'], ['group.seismik.org', '/grupo/']]) {
      await worker.fetch(new Request(`https://${host}/`), {});
      assert.equal(new URL(requests.at(-1).url).pathname, path);
    }
  } finally { globalThis.fetch = original; }
});


