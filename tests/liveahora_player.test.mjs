import {test} from 'node:test';
import assert from 'node:assert/strict';
import {youtubeVideoID, openViewer, safeImage} from '../web/liveahora/events.js';

test('An exact YouTube video is extracted without accepting channels or lookalike hosts', () => {
  for (const url of ['https://youtube.com/watch?v=M7lc1UVf-VE', 'https://youtu.be/M7lc1UVf-VE?t=30', 'https://www.youtube.com/live/M7lc1UVf-VE', 'https://youtube.com/shorts/M7lc1UVf-VE']) assert.equal(youtubeVideoID(url), 'M7lc1UVf-VE');
  for (const url of ['https://youtube.com/LiveAhoraES', 'https://youtube.com/watch?v=M7lc1UVf-VE&v=aaaaaaaaaaa', 'https://youtube.com.attacker.test/watch?v=M7lc1UVf-VE', 'https://youtu.be/watch?v=M7lc1UVf-VE', 'javascript:alert(1)', 'https://youtube.com/watch?v=<script>']) assert.equal(youtubeVideoID(url), null);
  assert.equal(safeImage('https://tracker.test/pixel.png'), false);
});

test('Player is created only on choice, uses the exact video and is removed on close', () => {
  const previous = globalThis.document;
  class Node {
    children = []; listeners = {}; textContent = '';
    constructor(tag) { this.tag = tag; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(key, value) { this[key] = value; }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    showModal() { this.open = true; }
    close() { this.open = false; this.listeners.close(); }
    remove() { this.removed = true; }
    focus() { this.focused = true; }
    set innerHTML(_) { throw new Error('HTML injection'); }
  }
  globalThis.document = {createElement: tag => new Node(tag), body:new Node('body')};
  try {
    const opener = new Node('a');
    const event = {title:'Exact video', platform:'youtube', url:'https://youtu.be/M7lc1UVf-VE'};
    openViewer(event, opener);
    const dialog = document.body.children[0];
    const player = dialog.children.find(node => node.className === 'video-player');
    const actions = dialog.children.find(node => node.className === 'video-actions');
    assert.equal(player.children.length, 0);
    actions.children.find(node => node.textContent === 'Mirar aquí').listeners.click();
    assert.equal(player.children[0].src, 'https://www.youtube-nocookie.com/embed/M7lc1UVf-VE?rel=0');
    assert.equal(player.children[0].referrerPolicy, 'strict-origin-when-cross-origin');
    dialog.close();
    assert.equal(player.children.length, 0);
    assert.equal(dialog.removed, true);
    assert.equal(opener.focused, true);
    for (const [platform,url] of [['youtube','https://youtube.com/LiveAhoraES'],['kick','https://kick.com/LiveAhoraES']]) {
      openViewer({...event,platform,url}, opener);
      const actions = document.body.children.at(-1).children.find(node => node.className === 'video-actions');
      assert.equal(actions.children.some(node => node.textContent === 'Mirar aquí'), false);
    }
  } finally { globalThis.document = previous; }
});
