// SPDX-License-Identifier: AGPL-3.0-only
// Run with node frontend/tests/auth-client.test.cjs; no browser/network required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(origin = 'https://belay.example.invalid') {
  const calls = [];
  const window = {
    location: { href: 'https://host.example.invalid/widget' },
    BELAY_AUTH_ORIGIN: origin,
    BELAY_GET_ACCESS_TOKEN: async () => 'short-lived-test-token',
    BELAY_INSTITUTION_ID: 'inst-a', BELAY_CLASS_ID: 'class-a',
  };
  const ctx = vm.createContext({ window, URL, fetch: async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => ({ ok: true }), text: async () => 'trace' };
  } });
  const root = path.join(__dirname, '..');
  vm.runInContext(fs.readFileSync(path.join(root, 'auth-client.js'), 'utf8'), ctx);
  // Evaluate the API module's functions in a hermetic VM (no import/network side effects).
  const api = fs.readFileSync(path.join(root, 'api-client.js'), 'utf8')
    .replace('import "./auth-client.js";', '')
    .replace(/export /g, '');
  vm.runInContext(api, ctx);
  return { window, ctx, calls };
}

test('all API calls, including export, carry bearer and scope headers', async () => {
  const { window, ctx, calls } = setup('http://localhost:8000');
  await vm.runInContext(`(async () => {
    await getCurriculum();
    await createParticipant('gh:1', true);
    await runModel('gh:1', 'echo-1', 'code');
    await solTurn({participantId:'gh:1', exerciseId:'echo-1'});
    await exportEvents('gh:1');
  })()`, ctx);
  assert.equal(calls.length, 5);
  for (const { url, options } of calls) {
    assert.equal(options.headers.Authorization, 'Bearer short-lived-test-token');
    assert.equal(options.headers['X-Belay-Institution'], 'inst-a');
    assert.equal(options.headers['X-Belay-Class'], 'class-a');
    assert.ok(!url.includes('token') && !url.includes('short-lived'));
  }
  window.BELAY_GET_ACCESS_TOKEN = async () => 'refreshed-test-token';
  await vm.runInContext('getCurriculum()', ctx);
  assert.equal(calls.at(-1).options.headers.Authorization, 'Bearer refreshed-test-token');
});

test('credentials never sent to changed origin, remote HTTP or URL credentials', async () => {
  const { window, calls } = setup();
  for (const base of ['https://attacker.invalid', 'http://belay.example.invalid',
                      'https://user:password@belay.example.invalid',
                      'https://belay.example.invalid?token=secret', 'https://belay.example.invalid#secret']) {
    await assert.rejects(window.BelayAuth.headers(base), /not configured/);
  }
  assert.equal(calls.length, 0);
});

test('missing or malformed access tokens fail closed', async () => {
  const { window } = setup();
  for (const token of ['', null, 'bad\r\nheader']) {
    window.BELAY_GET_ACCESS_TOKEN = async () => token;
    await assert.rejects(window.BelayAuth.headers(window.BELAY_AUTH_ORIGIN), /access token/);
  }
  delete window.BELAY_GET_ACCESS_TOKEN;
  await assert.rejects(window.BelayAuth.headers(window.BELAY_AUTH_ORIGIN), /not configured/);
});

test('all three demo POST paths call the shared credential helper', () => {
  for (const file of ['widget.html', 'embed-demo.html', 'dev-client.html']) {
    const html = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
    assert.match(html, /src="auth-client\.js"/);
    assert.match(html, /headers: await window\.BelayAuth\.headers/);
  }
});
