import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import worker from '../deploy/cloudflare-edge-router.js';
import { recordProbe, readHistory } from '../deploy/status-history.js';
import { STATUS_ASSETS } from '../deploy/status-assets.js';

function database() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec('CREATE TABLE probes (minute INTEGER PRIMARY KEY, api INTEGER, web INTEGER, developers INTEGER)');
  return { prepare(sql) { return { bind(...args) { return {
    async run() { return sqlite.prepare(sql).run(...args); },
    async all() { return { results: sqlite.prepare(sql).all(...args) }; },
  }; } }; } };
}

test('past failures survive retries and unobserved days remain unknown', async () => {
  const db = database();
  const now = Date.UTC(2026, 9, 7, 12);
  await recordProbe(db, { services: { api: true, web: false, developers: true } }, now - 86_400_000);
  await recordProbe(db, { services: { api: true, web: true, developers: true } }, now);
  await recordProbe(db, { services: { api: true, web: true, developers: true } }, now - 86_400_000);
  const history = await readHistory(db, now);
  assert.equal(history.days.length, 30);
  assert.equal(history.days[0].samples, 0);
  assert.equal(history.days[28].date, '2026-10-06');
  assert.equal(history.days[28].services.web.failed, 1);
  assert.equal(history.days[29].services.web.healthy, 1);
  assert.deepEqual(await readHistory(undefined, now), { available: false, days: [] });
});

test('cron records probes even without page visits', async () => {
  const db = database();
  const original = globalThis.fetch;
  const now = Date.UTC(2026, 9, 7, 12);
  let pending;
  globalThis.fetch = async url => new Response('', { status: String(url).endsWith('/health/ready') ? 503 : 200 });
  try {
    await worker.scheduled({ scheduledTime: now }, { STATUS_DB: db }, { waitUntil(p) { pending = p; } });
    await pending;
    const history = await readHistory(db, now);
    assert.equal(history.days[29].services.api.failed, 1);
    assert.equal(history.days[29].services.web.healthy, 1);
  } finally { globalThis.fetch = original; }
});

test('history and page work when the web origin is down', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('origin down'); };
  try {
    for (const path of ['/', '/status.html', '/status.js', '/status.css']) {
      const response = await worker.fetch(new Request(`https://status.seismik.org${path}`), {});
      assert.equal(response.status, 200);
      assert.equal(await response.text(), STATUS_ASSETS[path]);
    }
    const response = await worker.fetch(new Request('https://status.seismik.org/api/history'), { STATUS_DB: database() });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.equal((await response.json()).days.length, 30);
    const failed = await worker.fetch(new Request('https://status.seismik.org/api/history'), { STATUS_DB: { prepare() { throw new Error('db unavailable'); } } });
    assert.equal(failed.status, 503);
  } finally { globalThis.fetch = original; }
  for (const name of ['status.html', 'status.js', 'status.css']) {
    assert.equal(STATUS_ASSETS[`/${name}`], readFileSync(`web/${name}`, 'utf8').replace(/\r\n/g, '\n'));
  }
  for (const path of ['wrangler.toml', 'edge-worker/wrangler.toml']) {
    assert.match(readFileSync(path, 'utf8'), /binding = "STATUS_DB"/);
    assert.match(readFileSync(path, 'utf8'), /crons = \["\* \* \* \* \*"\]/);
  }
});
