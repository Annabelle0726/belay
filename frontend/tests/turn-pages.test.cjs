const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const read = (name) => fs.readFileSync(path.join(__dirname, "..", name), "utf8");
const reply = (data, status = 200) => ({ ok: status < 300, status, headers: new Headers(), json: async () => data });
const bubbles = ui => {
 const out=[];const walk=e=>{if((e.className||'').split(' ').includes('bubble'))out.push(e);for(const c of e.children||[])walk(c);};
 walk(ui.nodes['chat-feed']);return out;
};
const flush = () => new Promise((resolve) => setImmediate(resolve));

async function page(name, fetchTurn, timeoutMs, sharedStorage, recoveredAnswer, readyError) {
  const nodes = {};
  function node() {
    return {
      value: "", textContent: "", innerHTML: "", style: {}, children: [], listeners: {},
      addEventListener(type, fn) { this.listeners[type] = fn; },
      appendChild(child) { this.children.push(child); if (!this.value && child.value) this.value = child.value; },
      replaceChildren() { this.children = []; this.textContent=""; },
      querySelectorAll() {return [];}, setAttribute() {},
    };
  }
  const html = read(name);
  for (const match of html.matchAll(/id="([^"]+)"/g)) nodes[match[1]] = node();
  Object.entries({ base: "http://test", backend: "http://test", pid: "gh:12345", ex: "ds-foundations", stance: "peer", mode: "study" })
    .forEach(([id, value]) => { if (nodes[id]) nodes[id].value = value; });
  const context = vm.createContext({
    document: { getElementById: (id) => nodes[id], createElement: node, createTextNode:text=>({textContent:text}) },
    URL,
    window: { location:{href:"http://test/"}, addEventListener() {}, BELAY_LEARNER_ID: "gh:12345", BelayAuth: { headers: async () => ({ "Content-Type": "application/json", Authorization: "Bearer signed-test" }) } },
    latestAnswer: recoveredAnswer,
    localStorage: sharedStorage || (() => { const values = new Map(); return { getItem: (k) => values.get(k) || null, setItem: (k, v) => values.set(k, v), removeItem: (k) => values.delete(k) }; })(),
    crypto: require("node:crypto").webcrypto,
    setTimeout, clearTimeout, AbortController, console,
    fetch: async (url, options) => {
      if (url.endsWith("/api/curriculum")) return reply({ modules: [{ exercises: [{ id: "ds-foundations", title: "test", prompt: "test", starter: "pass" }] }] });
      if (url.endsWith("/jobs/config")) return reply({ recovery_scope: "a".repeat(64), learner_id: "gh:12345", assignments: {"ds-foundations":"v1", "ex":"v1", "echo-1":"v1"}, poll_seconds: 1, result_seconds: 300, notice: "Temporary encrypted recovery." });
      if (url.includes("/jobs/by-request/")) return reply({ id: "b".repeat(64), state: "completed", result: context.latestAnswer });
      const response = await fetchTurn(url, options);
      if (url.endsWith("/jobs") && response.ok) {
        let data;
        try { data = await response.json(); } catch { return response; }
        if (data && typeof data.message === "string") {
          context.latestAnswer = data;
          return reply({ id: "b".repeat(64), state: "queued" }, 202);
        }
        return reply(data);
      }
      return response;
    },
  });
  context.window.BelayConversations = {mount({renderHistory}) {
    const session={enabled:false,authorized:true,key:'test-scope',cid:null,revision:0,
      config:{identity:{learner_id:'gh:12345',institution_id:'i',class_id:'c'}}};
    renderHistory([],session);
    return {send:async()=>null,ready:async()=>{if(readyError)throw readyError;return session;},refresh:async()=>{}};
  }};
  vm.runInContext(read("control-messages.js"), context);
  vm.runInContext(read("request-lifecycle.js"), context);
  vm.runInContext(read("ask-jobs.js"), context);
  if (timeoutMs) {
    const request = context.belayRequestJSON;
    context.belayRequestJSON = (url, options, config) => request(url, options, { ...config, timeoutMs });
  }
  for (const match of html.matchAll(/<script(?: type="module")?>([\s\S]*?)<\/script>/g)) vm.runInContext(match[1], context);
  if(name === "dev-client.html") vm.runInContext(read("dev-client.js"),context);
  for(let n=0;n<12;n++) await flush();
  if(nodes.say) nodes.say.value="my question";
  if(nodes.question) nodes.question.value="my question";
  // Dev page's initial curriculum load.
  return { nodes, context, click: (id) => nodes[id].listeners.click(), change: (id) => nodes[id].listeners.change() };
}

for (const name of ["widget.html", "dev-client.html"]) {
  const widget = name === "widget.html";
  const send = widget ? "send" : "ask", status = widget ? "turnstatus" : "status";

  test(`${name}: network failure clears waiting, preserves input/answer, blocks repeat`, async () => {
    let calls = 0;
    const ui = await page(name, async () => { calls++; throw new TypeError("network lost"); });
    // The second click checks the existing pointer; it must not send another POST.
    ui.context.latestAnswer={message:"Recovered"};
    ui.nodes[widget ? "say" : "question"].value = "my question";
    if (!widget) ui.nodes["signals-status"].textContent = "earlier valid answer";
    await ui.click(send);
    assert.match(ui.nodes[status].textContent, /may still be running/);
    const preserved=ui.nodes[widget ? "say" : "question"].value;
    await ui.click(send);
    assert.equal(calls, 1);
    assert.equal(preserved,"my question");
  });

  test(`${name}: malformed/empty success never renders a successful answer`, async () => {
    for (const response of [{ ok: true, json: async () => { throw new SyntaxError(); } }, reply({})]) {
      const ui = await page(name, async () => response);
      await ui.click(send);
      assert.match(ui.nodes[status].textContent, /valid answer was not received/);
      if (widget) assert.equal(ui.nodes.msgs.children.length, 0);
      else assert.notEqual(ui.nodes["signals-status"].textContent, undefined);
    }
  });

  test(`${name}: double click sends once and stale response cannot publish after switching back`, async () => {
    let resolve, calls = 0;
    const ui = await page(name, () => { calls++; return new Promise((done) => { resolve = done; }); });
    const pending = ui.click(send);
    await flush(); await flush();
    await ui.click(send);
    const id = widget ? "ex" : "exercise";
    ui.nodes[id].value = "other"; ui.change(id);
    ui.nodes[id].value = "ds-foundations"; ui.change(id);
    await flush();
    resolve(reply({ message: "STALE", memory: {} }));
    await pending;
    assert.equal(calls, 1);
    if (widget) assert.equal(ui.nodes.msgs.children.length, 0);
    else assert.notEqual(ui.nodes["signals-status"].textContent, "STALE");
    assert.equal(ui.nodes[send].disabled, false);
    // Stale reply never overwrites the current context.
  });

  test(`${name}: stalled response body stops showing thinking`, async () => {
    const ui = await page(name, async () => ({ ok: true, json: () => new Promise(() => {}) }), 5);
    await ui.click(send);
    assert.match(ui.nodes[status].textContent, /Waiting timed out/);
    assert.equal(ui.nodes[send].disabled, false);
  });

  test(`${name}: valid answer remains usable without optional telemetry`, async () => {
    const ui = await page(name, async () => reply({ message: "Useful answer" }));
    await ui.click(send);
    assert.equal(ui.nodes[status].textContent, "");
    assert.equal(ui.nodes[send].disabled, false);
    if (widget) assert.match(ui.nodes.msgs.children.at(-1).innerHTML, /Useful answer/);
    else assert.match(bubbles(ui).at(-1).innerHTML, /Useful answer/);
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
  vm.runInContext("{ " + read("api-client.js").replace(/^import .*;$/gm, "").replace(/^export /gm, "") + "; globalThis.testSolTurn = solTurn; }", ui.context);
  await assert.rejects(ui.context.testSolTurn({ participantId: "p", exerciseId: "ex" }), { code: "invalid_response", uncertain: true });
});


for (const name of ["widget.html", "dev-client.html"]) {
  test(`${name}: reload recovers a lost POST with the stored pointer and no second POST`, async () => {
    const values = new Map();
    const store = {getItem: (k) => values.get(k) || null, setItem:(k,v) => values.set(k,v), removeItem:(k) => values.delete(k)};
    let posts = 0;
    const first = await page(name, async () => {posts++; throw TypeError("lost after admission");}, undefined, store);
    await first.click(name === "widget.html" ? "send" : "ask");
    assert.equal(posts,1);
    const second = await page(name, async () => {posts++; throw Error("must not resubmit");}, undefined, store, {message:"RECOVERED"});
    assert.equal(posts,1);
    if (name === "widget.html") assert.match(second.nodes.msgs.children[0].innerHTML,/RECOVERED/);
    else assert.equal(bubbles(second).at(-1).innerHTML,"RECOVERED");
    assert.match(second.nodes[name === "widget.html" ? "turnstatus" : "status"].textContent,/Recovered/);
    assert.equal(second.nodes[name === "widget.html" ? "send" : "ask"].disabled,false);
  });
}


test('minimal embed uses controlled Ask and blocks double clicks while one POST is outstanding',async()=>{
 let finish,posts=0;
 const ui=await page('embed-demo.html',()=>{posts++;return new Promise(resolve=>finish=resolve);});
 const first=ui.click('run');await flush();await flush();await ui.click('run');
 assert.equal(posts,1);finish(reply({message:'Embedded answer'}));await first;
 assert.match(ui.nodes.out.textContent,/Embedded answer/);assert.equal(ui.nodes.run.disabled,false);
});

for(const name of ['widget.html','dev-client.html']) test(name+': recovering old request preserves new input without inventing a student message',async()=>{
 let posts=0;const widget=name==='widget.html',input=widget?'say':'question';
 const ui=await page(name,()=>{posts++;throw TypeError('lost');});
 ui.nodes[input].value='Original';await ui.click(widget?'send':'ask');
 ui.context.latestAnswer={message:'Original reply'};ui.nodes[input].value='Not submitted';
 await ui.click(widget?'send':'ask');assert.equal(posts,1);assert.equal(ui.nodes[input].value,'Not submitted');
 assert.match(ui.nodes[widget?'turnstatus':'status'].textContent,/current input was not submitted/);
 if(widget) assert.equal(ui.nodes.msgs.children.length,1);
 else {assert.equal(bubbles(ui).filter(e=>e.className.includes('bubble-tutor')).length,1); assert.ok(bubbles(ui).every(e=>e.textContent!=='Not submitted'));}
});

for (const name of ['widget.html','dev-client.html','embed-demo.html']) test(name+': denied recovery scope is shown without an unhandled rejection',async()=>{
 const ui=await page(name,()=>{throw Error('No submission allowed');},undefined,undefined,undefined,Error('This exercise version is unavailable.'));
 const status=name==='widget.html'?'turnstatus':name==='dev-client.html'?'status':'out';
 assert.match(ui.nodes[status].textContent,/exercise version is unavailable/);
});
