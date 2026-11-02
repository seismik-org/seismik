import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../web/showcase.js', import.meta.url), 'utf8');

class Element {
  children = []; textContent = ''; attributes = {}; listeners = {};
  constructor(tag) { this.tag = tag; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  set innerHTML(_) { throw new Error('Unsafe HTML'); }
}
const descendants = node => [node, ...node.children.flatMap(descendants)];
const report = (agency, magnitude, depth_km) => ({
  event_id: `${agency}:earthquake`, agency, magnitude, depth_km, magnitude_type: 'Mw',
  origin_time: '2026-11-02T12:00:00Z', place: `Lugar según ${agency}`,
  official_url: `https://${agency.toLowerCase()}.example/earthquake`,
});

async function render(events, ok = true) {
  const list = new Element('ul'), status = new Element('p');
  vm.runInNewContext(source, {
    document: { querySelector: id => id === '#showcase-list' ? list : status,
      createElement: tag => new Element(tag) },
    Date, URL, fetch: async () => ({ ok, status: 503, json: async () => ({ events }) }),
  });
  await new Promise(resolve => setImmediate(resolve));
  return { list, status };
}

test('one card changes all source-dependent values and links when selecting an agency', async () => {
  const usgs = report('USGS', 5.3, 48.5), emsc = report('EMSC', 5.1, 24);
  const { list } = await render([{ ...usgs, source_reports: [usgs, emsc] }]);
  assert.equal(list.children.length, 1);
  const nodes = descendants(list), select = nodes.find(n => n.tag === 'select');
  assert.match(select.attributes['aria-label'], /Agencia del reporte/);
  assert.deepEqual(select.children.map(n => n.textContent), ['USGS', 'EMSC']);
  const badge = nodes.find(n => n.className?.startsWith('showcase-badge'));
  const meta = nodes.find(n => n.className === 'showcase-meta');
  const links = nodes.filter(n => n.tag === 'a');
  assert.equal(badge.textContent, '5.3 Mw');
  select.value = '1'; select.listeners.change();
  assert.equal(badge.textContent, '5.1 Mw');
  assert.match(meta.textContent, /EMSC.*24 km/);
  assert.equal(nodes.find(n => n.className === 'showcase-place').textContent, emsc.place);
  assert.equal(links[0].href, emsc.official_url);
  assert.equal(links[1].href, 'https://ifeltit.seismik.org/?event=EMSC%3Aearthquake');
  assert.equal(list.children.length, 1);
  assert.equal(descendants(list).find(n => n.tag === 'select'), select);
});

test('a single-agency card works with both the previous and new API response', async () => {
  for (const event of [report('USGS', 4.7, 10), { ...report('USGS', 4.7, 10), source_reports: [report('USGS', 4.7, 10)] }]) {
    const { list } = await render([event]);
    assert.equal(list.children.length, 1);
    assert.equal(descendants(list).some(n => n.tag === 'select'), false);
  }
});

test('agency text is rendered as text and unsafe source links are hidden', async () => {
  const event = { ...report('USGS', 4.7, 10), place: '<script>alert(1)</script>', official_url: 'javascript:alert(1)' };
  const { list } = await render([event]);
  const nodes = descendants(list);
  assert.equal(nodes.find(n => n.className === 'showcase-place').textContent, event.place);
  assert.equal(nodes.find(n => n.tag === 'a').hidden, true);
});

test('empty and failed responses explain the state without leaving placeholders', async () => {
  for (const ok of [true, false]) {
    const { list, status } = await render([], ok);
    assert.equal(list.children.length, 0);
    assert.match(status.textContent, ok ? /Sin sismos/ : /No se pudo cargar/);
  }
});
