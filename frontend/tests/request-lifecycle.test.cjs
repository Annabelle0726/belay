const assert = require("node:assert/strict");
const test = require("node:test");
require("../control-messages.js");
require("../request-lifecycle.js");

const reply = (data, status = 200) => ({ ok: status < 300, status, headers: new Headers(), json: async () => data });

test("network loss is uncertain and never retried", async () => {
  let calls = 0;
  global.fetch = async () => { calls++; throw new TypeError("PRIVATE network diagnostic"); };
  await assert.rejects(belayRequestJSON("/turn", { method: "POST" }), (error) => {
    assert.equal(error.uncertain, true);
    assert.match(error.message, /may still be running/);
    assert.doesNotMatch(error.message, /PRIVATE|try again later/);
    return true;
  });
  assert.equal(calls, 1);
});

test("deadline covers both stalled fetch and stalled response body", async () => {
  for (const bodyStalls of [false, true]) {
    let signal;
    global.fetch = (url, options) => {
      signal = options.signal;
      return bodyStalls ? Promise.resolve({ ok: true, json: () => new Promise(() => {}) }) : new Promise(() => {});
    };
    await assert.rejects(belayRequestJSON("/turn", {}, { timeoutMs: 5 }), { code: "request_timeout", uncertain: true });
    assert.equal(signal.aborted, true);
  }
});

test("invalid JSON and unusable turn shapes are not successes", async () => {
  const responses = [
    { ok: true, json: async () => { throw new SyntaxError(); } },
    ...[null, {}, { message: " " }, { message: "answer", memory: { grasped: "bad" } },
      { message: "answer", components: { overlay_declined: "bad" } }].map((data) => reply(data)),
  ];
  for (const response of responses) {
    global.fetch = async () => response;
    await assert.rejects(belayRequestJSON("/turn", {}, { validate: belayValidateTurn }), { code: "invalid_response", uncertain: true });
  }
});

test("known denials differ from ambiguous server errors without leaking diagnostics", async () => {
  global.fetch = async () => ({ ...reply({ detail: { code: "rate_limited" } }, 429), headers: new Headers({ "Retry-After": "3" }) });
  await assert.rejects(belayRequestJSON("/turn"), (error) => !error.uncertain && /3 seconds/.test(error.message));
  global.fetch = async () => reply({ detail: { code: "verified_execution_required" } }, 503);
  await assert.rejects(belayRequestJSON("/turn"), { uncertain: false });
  global.fetch = async () => reply({ detail: "PRIVATE provider diagnostic" }, 502);
  await assert.rejects(belayRequestJSON("/turn"), (error) => error.uncertain && !/PRIVATE|retry/.test(error.message));
});

test("gate blocks duplicates and uncertain replay and fences switch-away/switch-back", () => {
  const gate = belayTurnGate();
  const token = gate.begin("A");
  assert.equal(gate.begin("A"), null);
  gate.invalidate();
  assert.equal(gate.current(token, "A"), false);
  gate.finish(token, true);
  assert.equal(gate.begin("A"), null);
  assert.ok(gate.begin("B"));
});
