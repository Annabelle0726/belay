const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const reply = (data, status = 200, headers = {}) => ({ ok: status < 300, status, headers: new Headers(headers), json: async () => data });
const storage = () => {
  const values = new Map();
  return { values, getItem: (k) => values.get(k) || null, setItem: (k, v) => values.set(k, v), removeItem: (k) => values.delete(k) };
};
const config = { recovery_scope: "a".repeat(64), learner_id: "gh:1", assignments: {"echo-1":"v1"}, poll_seconds: 1, result_seconds: 300, notice: "Temporary encrypted recovery." };
const body = { exercise_id: "echo-1", source: "PRIVATE learner code", recent: [{who:"student",text:"PRIVATE prompt"}] };
const completed = {id:"b".repeat(64), state:"completed", result:{message:"useful answer"}};
let ids = 0;
function client(store, fetchJob, options = {}) {
  const calls = [];
  const context = vm.createContext({
    window: {BelayAuth:{headers:async () => ({Authorization:"Bearer PRIVATE_TOKEN"})}},
    setTimeout, clearTimeout, AbortController,
    fetch: async (url, opts) => {
      calls.push({url, opts});
      if (url.endsWith("/config") && options.configLost) throw TypeError('config disconnected');
      return url.endsWith("/config") ? reply(options.config || config) : fetchJob(url, opts);
    },
  });
  for (const name of ["control-messages.js", "request-lifecycle.js", "ask-jobs.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "..", name), "utf8"), context);
  return {calls, context, jobs: context.belayAskJobs({storage:store, uuid:() => `logical_request_${String(++ids).padStart(5,"0")}`, wait:async () => {}, ...options})};
}

test("lost admission response reloads the same request with GET and never stores text/token", async () => {
  const store = storage(); let posts = 0, id;
  const first = client(store, async (url, opts) => {
    assert.equal(opts.method, "POST"); posts++;
    id = JSON.parse(opts.body).request_id;
    assert.ok([...store.values.values()].some((v) => v.includes(id))); // persisted before send
    throw new TypeError("lost acknowledgement after server accepted");
  });
  await assert.rejects(first.jobs.ask("https://test", "/jobs", body), {uncertain:true});
  const reloaded = client(store, async (url, opts) => {
    assert.notEqual(opts.method, "POST"); assert.ok(url.endsWith(id)); return reply(completed);
  });
  assert.equal((await reloaded.jobs.recover("https://test", "/jobs", "echo-1")).message, "useful answer");
  assert.equal(posts, 1);
  assert.doesNotMatch(JSON.stringify([...store.values]), /PRIVATE|Bearer|useful answer/);
});

test("unknown or missing old job blocks automatic resend even with changed input", async () => {
  for (const response of [reply({...completed, state:"unknown", result:null}), reply({detail:{code:"job_unavailable"}},404)]) {
    let posts = 0;
    const store = storage();
    const value = client(store, async (url, opts) => {
      if (opts.method === "POST") {posts++; return reply({id:completed.id,state:"queued"},202);}
      return response;
    });
    await assert.rejects(value.jobs.ask("https://test","/jobs",body), {uncertain:true});
    await assert.rejects(value.jobs.ask("https://test","/jobs",{...body,source:"changed"}), {uncertain:true});
    assert.equal(posts,1);
    const reload = client(store, async () => response);
    await assert.rejects(reload.jobs.recover("https://test","/jobs","echo-1"), {uncertain:true});
    assert.equal(reload.calls.filter((c) => c.opts.method === "POST").length,0);
  }
});

test("queued/running polling and Retry-After keep one admission", async () => {
  const states = [reply({detail:{code:"poll_limited"}},429,{"Retry-After":"1"}),
    reply({...completed,state:"queued"}), reply({...completed,state:"running"}), reply(completed)];
  const waits = [], visible = [];
  const value = client(storage(), async (url, opts) => opts.method === "POST"
    ? reply({id:completed.id,state:"queued"},202) : states.shift(), {wait:async (ms) => waits.push(ms)});
  assert.equal((await value.jobs.ask("https://test","/jobs",body,(state) => visible.push(state))).message,"useful answer");
  assert.equal(value.calls.filter((c) => c.opts.method === "POST").length,1);
  assert.deepEqual(visible,["preparing","queued","running","completed"]);
  assert.deepEqual(waits,[1000,1000,1000]);
});

test("blocked storage refuses admission and invalid results remain pending", async () => {
  const blocked = client({getItem:() => null,setItem:() => {throw Error();}}, async () => {throw Error("must not send");});
  await assert.rejects(blocked.jobs.ask("https://test","/jobs",body), {code:"recovery_unavailable"});
  assert.equal(blocked.calls.length,1); // config only
  const store = storage();
  const invalid = client(store, async (url,opts) => reply(opts.method === "POST"
    ? {id:completed.id,state:"queued"} : {...completed,result:{message:" "}}));
  await assert.rejects(invalid.jobs.ask("https://test","/jobs",body), {code:"invalid_response",uncertain:true});
  assert.ok(JSON.parse([...store.values.values()][0]).pending);
});

test("result expiry never automatically posts; a new explicit Ask gets a new ID", async () => {
  const sent = [];
  const value = client(storage(), async (url,opts) => {
    if (opts.method === "POST") {sent.push(JSON.parse(opts.body).request_id);return reply({id:completed.id,state:"queued"});}
    return reply({...completed,state:"result_expired",reason:"result_expired",result:null});
  });
  await assert.rejects(value.jobs.ask("https://test","/jobs",body), {code:"result_expired",uncertain:false});
  assert.equal(sent.length,1);
  await assert.rejects(value.jobs.ask("https://test","/jobs",body), {code:"result_expired"});
  assert.equal(new Set(sent).size,2);
});

test("changed original subject scopes recovery pointer without querying old job", async () => {
  const store = storage();
  const first = client(store, async () => {throw TypeError();});
  await assert.rejects(first.jobs.ask("https://test","/jobs",body));
  const other = client(store, async () => {throw Error("must not query old subject job");},
    {config:{...config,recovery_scope:"c".repeat(64)}});
  assert.equal(await other.jobs.recover("https://test","/jobs","echo-1"),null);
  assert.equal(other.calls.length,1);
});


test("stalled credential refresh is bounded and late credentials never send a POST", async () => {
  const value = client(storage(), async () => {throw Error("must not send");}, {timeoutMs:5});
  let resume;
  value.context.window.BelayAuth.headers = () => new Promise((resolve) => {resume=resolve;});
  await assert.rejects(value.jobs.ask("https://test","/jobs",body), {code:"request_timeout",uncertain:false,notSubmitted:true});
  resume({Authorization:"Bearer late"});
  await new Promise((r) => setImmediate(r));
  assert.equal(value.calls.length,0);
});

test("unrendered completed response stays recoverable and cannot create a fresh paid turn", async () => {
  let posts=0;
  const store=storage();
  const value=client(store,async (url,opts) => {
    if (opts.method === "POST") {posts++; return reply({id:completed.id,state:"queued"});}
    return reply(completed);
  });
  await value.jobs.ask("https://test","/jobs",body); // Simulate a stale UI discarding the answer.
  assert.equal(JSON.parse([...store.values.values()][0]).pending,true);
  const rendered=await value.jobs.ask("https://test","/jobs",{...body,source:"different"});
  assert.equal(posts,1);
  value.jobs.acknowledge(rendered);
  assert.equal(JSON.parse([...store.values.values()][0]).pending,false);
});


test("third-party browser storage getter failure cannot break initialization or send", async () => {
  const value = client(undefined, async () => {throw Error("must not send");});
  Object.defineProperty(value.context,"localStorage",{get:() => {throw Error("blocked third-party storage");}});
  await assert.rejects(value.jobs.ask("https://test","/jobs",body),{code:"recovery_unavailable"});
  assert.equal(value.calls.length,1);
});

test('configuration network failure never implies a new execution and preserves a previous unknown pointer',async()=>{
 const store=storage();const first=client(store,async()=>{throw TypeError('lost admission');});
 await assert.rejects(first.jobs.ask('https://test','/jobs',body),{uncertain:true});
 const before=JSON.stringify([...store.values]);
 const broken=client(store,async()=>{throw Error('must not send');},{configLost:true});
 await assert.rejects(broken.jobs.ask('https://test','/jobs',body),{uncertain:false,notSubmitted:true,phase:'configuration'});
 assert.equal(JSON.stringify([...store.values]),before);assert.equal(broken.calls.length,1);
});

test('definite admission setup denial retains a rejected receipt without phantom polling; restored service needs an intentional Ask',async()=>{
 const store=storage();let posts=0;
 const denied=client(store,async(url,opts)=>{
  assert.equal(opts.method,'POST');posts++;return reply({detail:{code:'jobs_disabled'}},503);
 });
 await assert.rejects(denied.jobs.ask('https://test','/jobs',body),{uncertain:false,notSubmitted:true});
 const receipt=JSON.parse([...store.values.values()][0]);assert.equal(receipt.pending,false);assert.equal(receipt.not_submitted,true);
 const restored=client(store,async(url,opts)=>{if(opts.method==='POST'){posts++;return reply({id:completed.id,state:'queued'},202);}return reply(completed);});
 assert.equal(await restored.jobs.recover('https://test','/jobs','echo-1'),null);assert.equal(posts,1);
 assert.equal((await restored.jobs.ask('https://test','/jobs',body)).message,'useful answer');assert.equal(posts,2);
});

test('recovery callback retains the logical ID even when the first GET loses its response', async()=>{
 const store=storage();const first=client(store,async()=>{throw TypeError('lost');});
 await assert.rejects(first.jobs.ask('https://test','/jobs',body),{uncertain:true});
 const id=JSON.parse([...store.values.values()][0]).request_id;
 const events=[];const next=client(store,async()=>{throw TypeError('offline');});
 await assert.rejects(next.jobs.recover('https://test','/jobs','echo-1',(state,config,ref)=>events.push(ref)),{request_id:id,uncertain:true});
 assert.equal(events[0].request_id,id);assert.equal(events[0].recovered,true);
 assert.equal(next.calls.some(c=>c.opts.method==='POST'),false);
});

test('server execution deadline is distinct from browser waiting timeout and retains unknown ID',async()=>{
 const store=storage();const value=client(store,async(url,opts)=>reply(opts.method==='POST'
  ? {id:completed.id,state:'queued'} : {id:completed.id,state:'unknown',reason:'execution_deadline'}));
 await assert.rejects(value.jobs.ask('https://test','/jobs',body),error=>{
  assert.equal(error.code,'execution_deadline');assert.equal(error.uncertain,true);
  assert.match(error.message,/server execution deadline/);assert.ok(error.request_id);return true;
 });
 assert.equal(JSON.parse([...store.values.values()][0]).pending,true);
});


test('old backend validation rejection records non-admission and never polls the rejected ID', async()=>{
 const store=storage();
 const rejected=client(store,async()=>reply({detail:[{type:'extra_forbidden',loc:['body','reply_to'],msg:'Extra inputs not permitted',input:{secret:'must not display'}}]},422),{config:{...config,reply_references:{version:1,passages:true}}});
 await assert.rejects(rejected.jobs.ask('https://test','/jobs',{...body,reply_to:{request_id:'prior_request_001'}}),{code:'request_invalid',notSubmitted:true,uncertain:false});
 const receipt=JSON.parse([...store.values.values()][0]);
 assert.equal(receipt.pending,false);assert.equal(receipt.not_submitted,true);
 const reload=client(store,async()=>{throw Error('no request for rejected ID');});
 assert.equal(await reload.jobs.recover('https://test','/jobs','echo-1'),null);
 assert.equal(reload.calls.length,1);
 const next=client(store,async(url,opts)=>reply(opts.method==='POST'?{id:completed.id,state:'queued'}:completed));
 const result=await next.jobs.ask('https://test','/jobs',body);
 assert.equal(result.message,'useful answer');
 assert.notEqual(JSON.parse(next.calls.find(c=>c.opts.method==='POST').opts.body).request_id,receipt.request_id);
});

test('unsupported quote capability does not create a pointer or erase an older pending request',async()=>{
 const store=storage();const old=client(store,async()=>{throw TypeError('lost');});
 await assert.rejects(old.jobs.ask('https://test','/jobs',body));
 const before=JSON.stringify([...store.values]);
 const value=client(store,async(url,opts)=>{assert.notEqual(opts.method,'POST');return reply({detail:{code:'job_unavailable'}},404);});
 await assert.rejects(value.jobs.ask('https://test','/jobs',{...body,reply_to:{request_id:'prior_request_001'}}),{uncertain:true});
 assert.equal(JSON.stringify([...store.values]),before);
 const empty=storage();const incompatible=client(empty,async()=>{throw Error('must not post');});
 await assert.rejects(incompatible.jobs.ask('https://test','/jobs',{...body,reply_to:{request_id:'prior_request_001'}}),{code:'reply_protocol_unavailable',notSubmitted:true});
 assert.equal(empty.values.size,0);
});


test('fresh admission budget or unstructured validation rejection never becomes a phantom unknown task',async()=>{
 for(const response of [reply({detail:'object required'},422),reply({detail:{code:'budget_exhausted'}},429)]) {
  const store=storage();const value=client(store,async()=>response);
  await assert.rejects(value.jobs.ask('https://test','/jobs',body),{notSubmitted:true,uncertain:false});
  assert.equal(JSON.parse([...store.values.values()][0]).pending,false);
  assert.equal(await value.jobs.recover('https://test','/jobs','echo-1'),null);
 }
});

test("missing legacy pointer is fenced before release, then requires a deliberate new Ask", async () => {
  const store=storage(); let old;
  const lost=client(store,async(url,opts)=>{old=JSON.parse(opts.body).request_id;throw TypeError('lost');});
  await assert.rejects(lost.jobs.ask('https://test','/jobs',body));
  const restored=client(store,async(url,opts)=>{
    if(url.endsWith('/reconcile')) {
      assert.equal(opts.method,'POST'); assert.equal(JSON.parse(opts.body).request_id,old);
      assert.equal(JSON.parse(opts.body).exercise_id,'echo-1');
      return reply({id:'c'.repeat(64),state:'failed',reason:'request_not_admitted'});
    }
    if(opts.method==='POST') return reply({id:completed.id,state:'queued'});
    if(url.endsWith(old)) return reply({detail:{code:'job_unavailable'}},404);
    return reply(completed);
  },{config:{...config,missing_request_recovery:1}});
  await assert.rejects(restored.jobs.ask('https://test','/jobs',body),{code:'request_not_admitted',uncertain:false,notSubmitted:true});
  assert.equal(restored.calls.filter(c=>c.url.endsWith('/by-request/'+old)).length,0);
  assert.equal(restored.calls.filter(c=>c.opts.method==='POST'&&!c.url.endsWith('/reconcile')).length,0);
  assert.equal(JSON.parse([...store.values.values()][0]).request_id,old);
  assert.equal(await restored.jobs.recover('https://test','/jobs','echo-1'),null);
  assert.equal((await restored.jobs.ask('https://test','/jobs',body)).message,'useful answer');
});

test("unconfirmed reconciliation keeps the original ID blocked without model submission", async () => {
  for(const failure of ['lost','foreign','unknown']) {
    const store=storage();
    const lost=client(store,async()=>{throw TypeError('lost');});
    await assert.rejects(lost.jobs.ask('https://test','/jobs',body));
    const before=JSON.stringify([...store.values]);
    const recovery=client(store,async(url)=>{
      if(url.endsWith('/reconcile')) {
        if(failure==='lost') throw TypeError('lost receipt');
        if(failure==='unknown') return reply({id:completed.id,state:'unknown'});
      }
      return reply({detail:{code:'job_unavailable'}},404);
    },{config:{...config,missing_request_recovery:1}});
    await assert.rejects(recovery.jobs.recover('https://test','/jobs','echo-1'),{uncertain:true});
    assert.equal(JSON.stringify([...store.values]),before);
    assert.equal(recovery.calls.filter(c=>c.opts.method==='POST'&&!c.url.endsWith('/reconcile')).length,0);
  }
});
