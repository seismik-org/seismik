import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../deploy/cloudflare-edge-router.js';

test('explore paths use the static origin and maps stay confined to that page', async () => {
  const previous=globalThis.fetch;
  const targets=[];
  globalThis.fetch=async request => { targets.push(request.url); return new Response('<html></html>',{headers:{'Content-Type':'text/html'}}); };
  try {
    for (const path of ['/explore','/explore/','/explore.html']) {
      const result=await worker.fetch(new Request('https://devs.seismik.org'+path),{});
      assert.match(targets.at(-1),/\/explore.html$/);
      assert.match(result.headers.get('Content-Security-Policy'),/https:\/\/tile.openstreetmap.org/);
      assert.equal(result.headers.get('Referrer-Policy'),'strict-origin-when-cross-origin');
    }
    const other=await worker.fetch(new Request('https://devs.seismik.org/'),{});
    assert.ok(!other.headers.get('Content-Security-Policy').includes('tile.openstreetmap.org'));
  } finally { globalThis.fetch=previous; }
});

test('session exploration is proxied privately and client origin secrets are replaced', async () => {
  const previous=globalThis.fetch;
  let target;
  globalThis.fetch=async request => { target=request; return Response.json({detail:'login required'},{status:401}); };
  try {
    const response=await worker.fetch(new Request('https://devs.seismik.org/v1/developer/explore/history',{
      headers:{'X-Seismik-Origin-Auth':'spoofed',Cookie:'seismik_session=example'},
    }),{EDGE_ORIGIN_SECRET:'test-only'});
    assert.match(target.url,/seismik-api-.*\/v1\/developer\/explore\/history$/);
    assert.equal(target.headers.get('X-Seismik-Origin-Auth'),'test-only');
    assert.equal(target.headers.get('Cookie'),'seismik_session=example');
    assert.equal(target.headers.get('X-Seismik-API-Key'),null);
    assert.equal(response.status,401);
    assert.equal(response.headers.get('Cache-Control'),'no-store');
    assert.ok(!JSON.stringify([...response.headers]).includes('test-only'));
  } finally { globalThis.fetch=previous; }
});
