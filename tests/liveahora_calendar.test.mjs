import {test} from 'node:test';
import assert from 'node:assert/strict';
import {safeEventURL, colombiaInput, toUTC, eventCard} from '../web/liveahora/events.js';

test('Colombia date entry round-trips across a UTC date boundary', () => {
  assert.equal(toUTC('2030-01-15T23:30'), '2030-01-16T04:30:00.000Z');
  assert.equal(colombiaInput('2030-01-16T04:30:00Z'), '2030-01-15T23:30');
  assert.equal(colombiaInput('2030-07-16T04:30:00Z'), '2030-07-15T23:30');
});

test('Only a real HTTPS URL on the selected streaming platform is linked', () => {
  assert.equal(safeEventURL('https://kick.com/LiveAhoraES','kick'), 'https://kick.com/LiveAhoraES');
  for (const bad of ['javascript:alert(1)', 'https://kick.com.attacker.example/a', 'https://user:pass@kick.com/a', 'http://kick.com/a', 'https://kick.com:8080/a', 'https://twitch.tv/LiveAhoraES']) {
    assert.equal(safeEventURL(bad, 'kick'), null);
  }
});

test('Cancelled events have no public watch button and descriptions are text', () => {
  const previous = globalThis.document;
  class Node {
    children = []; textContent = '';
    constructor(tag) { this.tag = tag; }
    append(...nodes) { this.children.push(...nodes); }
    set innerHTML(_) { throw new Error('HTML injection'); }
  }
  globalThis.document = {createElement: tag => new Node(tag)};
  try {
    const event = {title:'<img src=x onerror=alert(1)>', description:'<script>alert(1)</script>', starts_at:'2030-01-01T12:00:00Z', status:'cancelled', platform:'youtube', url:'https://youtube.com/LiveAhoraES'};
    const card = eventCard(event);
    const copy = card.children[0];
    assert.equal(copy.children.find(node => node.tag === 'h3').textContent, event.title);
    assert.equal(copy.children.find(node => node.textContent === event.description).tag, 'p');
    assert.equal(copy.children.some(node => node.tag === 'a'), false);
    assert.equal(eventCard({...event, status:'scheduled'}).children[0].children.some(node => node.tag === 'a'), true);
  } finally { globalThis.document = previous; }
});
