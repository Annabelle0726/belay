// SPDX-License-Identifier: AGPL-3.0-only
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {setTimeout: delay} = require('node:timers/promises');
const {JSDOM, ResourceLoader} = require('jsdom');

test('fresh offline preview loads all fixture exercises without a connection change', async () => {
  const root = path.resolve(__dirname, '..');
  const generated = execFileSync(process.execPath, [path.join(__dirname, 'build-feedback-fixture.cjs')], {encoding:'utf8'}).trim();
  class Scripts extends ResourceLoader {
    fetch(url, {element}) {
      if (element.localName !== 'script') return null;
      const script = new URL(url);
      assert.equal(script.origin, 'https://preview.invalid');
      return Promise.resolve(fs.readFileSync(path.join(root, script.pathname.slice(1))));
    }
  }
  const dom = new JSDOM(fs.readFileSync(generated, 'utf8'), {
    url:'https://preview.invalid/tests/fixtures/generated-feedback-preview.html',
    resources:new Scripts(), runScripts:'dangerously',
    beforeParse(window) {Object.assign(window, {Response, Headers, Request, matchMedia:()=>({matches:false,addEventListener(){}})});}
  });
  try {
    const options = () => Array.from(dom.window.document.querySelectorAll('#exercise option'), o => o.value);
    for (let i=0; i<60 && !options().includes('ds-mlp'); i++) await delay(50);
    assert.deepEqual(options(), ['ds-foundations','ds-regression','ds-mlp']);
  } finally {dom.window.close();}
});
