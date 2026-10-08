// SPDX-License-Identifier: AGPL-3.0-only
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../theme-client.js'), 'utf8');
function setup(stored, blocked = false) {
  const listeners = {}, writes = [];
  const picker = {value: '', addEventListener(type, fn) {listeners[type] = fn;}};
  const root = {dataset: {}};
  const media = {matches: true, addEventListener(_, fn) {this.change = fn;}};
  const document = {documentElement: root, querySelectorAll: () => [picker],
    addEventListener(_, fn) {this.ready = fn;}};
  const window = {matchMedia: () => media, localStorage: {
    getItem() {if (blocked) throw Error('unavailable'); return stored;},
    setItem(key, value) {if (blocked) throw Error('unavailable'); writes.push([key, value]);}
  }};
  vm.runInNewContext(source, {window, document}); document.ready();
  return {root, media, picker, writes, choose(value) {picker.value = value; listeners.change();}};
}
test('system default follows OS changes; explicit theme overrides them', () => {
  const s = setup(null);
  assert.equal(s.root.dataset.theme, 'light');
  s.media.matches = false; s.media.change();
  assert.equal(s.root.dataset.theme, 'dark');
  s.choose('light'); s.media.change();
  assert.equal(s.root.dataset.theme, 'light');
  s.choose('auto'); assert.equal(s.root.dataset.theme, 'dark');
});
test('only a validated display preference is persisted and restored', () => {
  const s = setup('dark');
  assert.equal(s.picker.value, 'dark');
  s.choose('light');
  assert.deepEqual(s.writes, [['sol-theme', 'light']]);
  s.choose('invalid'); assert.equal(s.root.dataset.themePref, 'light');
  assert.equal(s.writes.length, 1);
  assert.equal(setup('invalid').root.dataset.themePref, 'auto');
});
test('embedded hosts without browser storage can still switch themes', () => {
  const s = setup(null, true); s.choose('dark');
  assert.equal(s.root.dataset.theme, 'dark');
  assert.equal(s.picker.value, 'dark');
});
