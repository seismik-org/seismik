import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
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

test('LiveAhora assets and navigation resolve; rights and contact are present without a fictitious live player', () => {
  for (const page of ['index.html', 'politicas/index.html', 'admin/index.html']) {
    const html = readFileSync(`web/liveahora/${page}`, 'utf8');
    assert.match(html, /CSN \(Creator Sports Network\)|Creator Sports Network/);
    assert.match(html, /mailto:liveahora@seismik.org/);
    assert.doesNotMatch(html, /<iframe|<video|autoplay|style="/i);
    for (const [, url] of html.matchAll(/(?:href|src)="(\/[^"#?]*)(?:[?#][^"]*)?"/g)) {
      const routed = new Map([['/', '/liveahora/'], ['/politicas/', '/liveahora/politicas/'], ['/admin/', '/liveahora/admin/']]).get(url) || url;
      if (!url.startsWith('/v1/')) assert.ok(existsSync(`web${routed}${routed.endsWith('/') ? 'index.html' : ''}`), `${page}: ${url}`);
    }
    const canonical = page.startsWith('politicas') ? 'politicas/' : page.startsWith('admin') ? 'admin/' : '';
    assert.ok(html.includes(`rel="canonical" href="https://liveahora.seismik.org/${canonical}"`));
  }
  const group = readFileSync('web/grupo/index.html', 'utf8');
  assert.match(group, /Cuatro iniciativas/);
  assert.match(group, /id="liveahora"/);
  assert.match(group, /https:\/\/liveahora.seismik.org\//);
});
