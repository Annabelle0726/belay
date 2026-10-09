const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const read = (name) => fs.readFileSync(path.join(__dirname, "..", name), "utf8");
const reply = (data, status = 200) => ({ ok: status < 300, status, headers: new Headers(), json: async () => data });
const flush = () => new Promise((resolve) => setImmediate(resolve));

async function page(name, fetchTurn, timeoutMs) {
  const nodes = {};
  function node() {
    return {
      value: "", textContent: "", innerHTML: "", style: {}, children: [], listeners: {},
      addEventListener(type, fn) { this.listeners[type] = fn; },
      appendChild(child) { this.children.push(child); if (!this.value && child.value) this.value = child.value; },
      replaceChildren() { this.children = []; },
    };
  }
  const html = read(name);
  for (const match of html.matchAll(/id="([^"]+)"/g)) nodes[match[1]] = node();
  Object.entries({ base: "http://test", backend: "http://test", pid: "gh:12345", ex: "ds-foundations", stance: "peer", mode: "study" })
    .forEach(([id, value]) => { if (nodes[id]) nodes[id].value = value; });
  const context = vm.createContext({
    document: { getElementById: (id) => nodes[id], createElement: node },
    setTimeout, clearTimeout, AbortController, console,
    fetch: (url, options) => url.endsWith("/api/curriculum")
      ? Promise.resolve(reply({ modules: [{ exercises: [{ id: "ds-foundations", title: "test", prompt: "test", starter: "pass" }] }] }))
      : fetchTurn(url, options),
  });
  vm.runInContext(read("control-messages.js"), context);
  vm.runInContext(read("request-lifecycle.js"), context);
  if (timeoutMs) {
    const request = context.belayRequestJSON;
    context.belayRequestJSON = (url, options, config) => request(url, options, { ...config, timeoutMs });
  }
  for (const match of html.matchAll(/<script(?: type="module")?>([\s\S]*?)<\/script>/g)) vm.runInContext(match[1], context);
  await flush(); // Dev page's initial curriculum load.
  return { nodes, context, click: (id) => nodes[id].listeners.click(), change: (id) => nodes[id].listeners.change() };
}

for (const name of ["widget.html", "dev-client.html"]) {
  const widget = name === "widget.html";
  const send = widget ? "send" : "ask", status = widget ? "turnstatus" : "status";

  test(`${name}: network failure clears waiting, preserves input/answer, blocks repeat`, async () => {
    let calls = 0;
    const ui = await page(name, async () => { calls++; throw new TypeError("network lost"); });
    ui.nodes[widget ? "say" : "source"].value = "my question";
    if (!widget) ui.nodes.solmsg.textContent = "earlier valid answer";
    await ui.click(send);
    await ui.click(send);
    assert.equal(calls, 1);
    assert.match(ui.nodes[status].textContent, /may still be running/);
    assert.equal(ui.nodes[send].disabled, true);
    assert.equal(ui.nodes[widget ? "say" : "source"].value, "my question");
    if (widget) assert.equal(ui.nodes.msgs.children.length, 1); // Student only; no blank tutor entry.
    else assert.equal(ui.nodes.solmsg.textContent, "earlier valid answer");
  });

  test(`${name}: malformed/empty success never renders a successful answer`, async () => {
    for (const response of [{ ok: true, json: async () => { throw new SyntaxError(); } }, reply({})]) {
      const ui = await page(name, async () => response);
      await ui.click(send);
      assert.match(ui.nodes[status].textContent, /valid answer was not received/);
      if (widget) assert.equal(ui.nodes.msgs.children.length, 0);
      else assert.notEqual(ui.nodes.solmsg.textContent, undefined);
    }
  });

  test(`${name}: double click sends once and stale response cannot publish after switching back`, async () => {
    let resolve, calls = 0;
    const ui = await page(name, () => { calls++; return new Promise((done) => { resolve = done; }); });
    const pending = ui.click(send);
    await ui.click(send);
    const id = widget ? "ex" : "exercise";
    ui.nodes[id].value = "other"; ui.change(id);
    ui.nodes[id].value = "ds-foundations"; ui.change(id);
    resolve(reply({ message: "STALE", memory: {} }));
    await pending;
    assert.equal(calls, 1);
    if (widget) assert.equal(ui.nodes.msgs.children.length, 0);
    else assert.notEqual(ui.nodes.solmsg.textContent, "STALE");
    assert.equal(ui.nodes[send].disabled, false);
    assert.equal(ui.nodes[status].textContent, "");
  });

  test(`${name}: stalled response body stops showing thinking`, async () => {
    const ui = await page(name, async () => ({ ok: true, json: () => new Promise(() => {}) }), 5);
    await ui.click(send);
    assert.match(ui.nodes[status].textContent, /Waiting timed out/);
    assert.equal(ui.nodes[send].disabled, true);
  });

  test(`${name}: valid answer remains usable without optional telemetry`, async () => {
    const ui = await page(name, async () => reply({ message: "Useful answer" }));
    await ui.click(send);
    assert.equal(ui.nodes[status].textContent, "");
    assert.equal(ui.nodes[send].disabled, false);
    if (widget) assert.match(ui.nodes.msgs.children[0].innerHTML, /Useful answer/);
    else assert.equal(ui.nodes.solmsg.textContent, "Useful answer");
  });

  test(`${name}: an explicit rate denial permits a later intentional request`, async () => {
    let calls = 0;
    const ui = await page(name, async () => ++calls === 1
      ? reply({ detail: { code: "rate_limited" } }, 429) : reply({ message: "answer" }));
    await ui.click(send);
    assert.equal(ui.nodes[send].disabled, false);
    await ui.click(send);
    assert.equal(calls, 2);
    assert.equal(ui.nodes[status].textContent, "");
  });
}

test("widget keeps the previous answer and confirmed history after a failed follow-up", async () => {
  let calls = 0;
  const ui = await page("widget.html", async () => {
    if (++calls === 1) return reply({ message: "earlier answer" });
    throw new TypeError("lost");
  });
  ui.nodes.say.value = "first question";
  await ui.click("send");
  ui.nodes.say.value = "follow-up";
  await ui.click("send");
  assert.match(ui.nodes.msgs.children[1].innerHTML, /earlier answer/);
  assert.equal(vm.runInContext("recent.length", ui.context), 2);
  assert.equal(ui.nodes.say.value, "follow-up");
});

test("widget auxiliary actions also surface HTTP failures without unhandled rejection", async () => {
  const ui = await page("widget.html", async () => reply({ detail: "PRIVATE" }, 502));
  for (const id of ["setgoal", "setrefl"]) await ui.click(id);
  await ui.change("knob");
  for (const id of ["goalstate", "reflstate", "declined"]) {
    assert.match(ui.nodes[id].textContent, /not confirmed/);
    assert.doesNotMatch(ui.nodes[id].textContent, /PRIVATE/);
  }
});

test("dev run failure cannot trigger a model turn or reuse an earlier run result", async () => {
  for (const failure of [reply({ ok: false, error: "compile failed" }), reply({ detail: "failed" }, 502)]) {
    const urls = [];
    const ui = await page("dev-client.html", async (url) => { urls.push(url); return failure; });
    await ui.click("run");
    assert.deepEqual(urls, ["http://test/api/run"]);
    assert.doesNotMatch(ui.nodes.status.textContent, /thinking/);
  }
});

test("API client uses the same validated transport for turns", async () => {
  const ui = await page("widget.html", async () => reply({}));
  // Exercise the module body in this isolated VM; imports were loaded above.
  vm.runInContext(read("api-client.js").replace(/^import .*;$/gm, "").replace(/^export /gm, ""), ui.context);
  await assert.rejects(ui.context.solTurn({ participantId: "p", exerciseId: "ex" }), { code: "invalid_response", uncertain: true });
});
