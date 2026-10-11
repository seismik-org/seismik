const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/theme.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
function setup() {
  const events = {}, root = { dataset: {} }, media = { matches: false, addEventListener: (_, fn) => { events.media = fn; } };
  vm.runInNewContext(source, { window: { matchMedia: () => media }, document: { documentElement: root } });
  return { root, media, events };
}
const device = setup();
assert.equal(device.root.dataset.theme, 'light');
device.media.matches = true; device.events.media();
assert.equal(device.root.dataset.theme, 'dark');
device.media.matches = false; device.events.media();
assert.equal(device.root.dataset.theme, 'light');
// Sin selector de apariencia y sin preferencia en el navegador.
assert.doesNotMatch(html, /id="theme"|theme-control|Apariencia/);
assert.doesNotMatch(source, /localStorage|getElementById/);
console.log('Theme: follows the device automatically; no appearance selector or stored preference.');
