// SPDX-License-Identifier: AGPL-3.0-only
// Exercise the real client and shared Session with a small DOM and offline API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

class Element {
  constructor(tag = 'div') { this.tagName=tag; this.children=[]; this.listeners={}; this.value=''; this.style={}; }
  set textContent(value) { this.text=value; this.children=[]; }
  get textContent() { return this.text || this.children.map(c=>c.textContent).join(''); }
  set innerHTML(value) { this.html=value; this.children=[]; }
  get innerHTML() { return this.html || ''; }
  appendChild(child) {
    if(child.parentElement) child.parentElement.children=child.parentElement.children.filter(c=>c!==child);
    this.children.push(child); child.parentElement=this;
    if(this.tagName==='select' && !this.value) this.value=child.value;
    return child;
  }
  replaceChildren(...children) { this.text=''; this.html=''; this.children=children; if(this.tagName==='select') this.value=''; }
  querySelectorAll() { return []; }
  addEventListener(event,handler) { this.listeners[event]=handler; }
  setAttribute(key,value) { this[key]=value; }
  async fire(event) { return this.listeners[event]?.({key:'Enter',preventDefault(){}}); }
}
const root=path.join(__dirname,'..');
const bubbles=env=>{
  const out=[];const walk=e=>{if((e.className||'').split(' ').includes('bubble'))out.push(e);for(const c of e.children||[])walk(c);};
  walk(env.nodes['chat-feed']);return out;
};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function setup(state={}) {
  state.entries ||= new Map(); state.attempts ||= new Map(); state.serial ||= 0;
  state.identity ||= {institution_id:'inst-a',class_id:'class-a',learner_id:'gh:1'};
  const calls=[],nodes={},handlers={};
  let dom;
  if (state.withMarkdown) {
    const {JSDOM}=require('jsdom');
    dom=new JSDOM(fs.readFileSync(path.join(root,'dev-client.html'),'utf8'),{
      url:'https://host.invalid',runScripts:'outside-only'});
    dom.window.HTMLElement.prototype.addEventListener=Element.prototype.addEventListener;
    dom.window.HTMLElement.prototype.fire=Element.prototype.fire;
    for(const file of ['marked.umd.js','purify.min.js','highlight.min.js'])
      dom.window.eval(fs.readFileSync(path.join(root,'vendor',file),'utf8'));
  }
  for(const id of ['backend','exercise','mode','source','question','status','result','prompt','chat-feed',
    'conversation-controls','ask','run','affect','interv','planner','selfeval','gov','mem','timings','conf','confbar','signals-status',
    'feedback-loading','feedback-announcement','glass-box','signals-storage']) {
    nodes[id]=dom ? dom.window.document.getElementById(id) : new Element(id==='exercise'?'select':'div');
    if(dom) nodes[id].listeners={};
  }
  nodes.backend.value='https://belay.invalid'; nodes.mode.value='study';
  nodes.ask.textContent='Ask Sol'; nodes.run.textContent='Run code';
  const window={location:{href:'https://host.invalid'+(state.search||'')},BELAY_AUTH_ORIGIN:'https://belay.invalid',
    BELAY_GET_ACCESS_TOKEN:async()=>'short-lived-token',BELAY_LEARNER_ID:'gh:1',
    BELAY_INSTITUTION_ID:'inst-a',BELAY_CLASS_ID:'class-a',crypto:{randomUUID:()=>`request-${++state.serial}`},
    addEventListener:(event,handler)=>handlers[event]=handler,
    localStorage:{getItem:key=>state.entries.get(key)||null,setItem:(key,value)=>state.entries.set(key,value),removeItem:key=>state.entries.delete(key)}};
  if(dom) Object.assign(window,{marked:dom.window.marked,DOMPurify:dom.window.DOMPurify,hljs:dom.window.hljs});
  const document=dom ? dom.window.document : {getElementById:id=>nodes[id],createElement:tag=>new Element(tag),
    createTextNode:text=>({textContent:text})};
  if(dom) {
    const create=document.createElement.bind(document);
    document.createElement=tag=>{const e=create(tag);e.listeners={};return e;};
  }
  const fetch=async(url,options)=>{
    calls.push({url,options});
    if(state.unauthorized) return {ok:false,status:401,headers:new Headers(),json:async()=>({detail:'invalid credentials'})};
    const body=options.body?JSON.parse(options.body):{};
    let result={},status=200;
    if(url.endsWith('/api/curriculum')) result={modules:[{exercises:[{id:'echo-1',title:'Echo',prompt:'Learn loops',starter:'print(1)'}]}]};
    else if(url.endsWith('/jobs/config')) {
      if(state.jobsConfigCode) {status=503;result={detail:{code:state.jobsConfigCode}};}
      else result={recovery_scope:'a'.repeat(64),learner_id:state.identity.learner_id,
        assignments:{'echo-1':'v1'},poll_seconds:1,result_seconds:300,notice:'Temporary recovery'};
    }
    else if(url.includes('/jobs/by-request/')) {
      if(state.pollStates?.length) result={id:'b'.repeat(64),state:state.pollStates.shift(),result:null};
      else if(state.pollTerminal) result={id:'b'.repeat(64),state:state.pollTerminal,reason:state.pollReason||'execution_failed',result:null};
      else if(state.unknown) result={id:'b'.repeat(64),state:'unknown',result:null};
      else if(url.includes('/conversations/')) result=state.savedResult;
      else result={id:'b'.repeat(64),state:'completed',result:{message:state.reply||'Live answer',components:{},memory:{}}};
    }
    else if(url.endsWith('/api/sol/jobs')) result={id:'b'.repeat(64),state:'queued'};
    else if(url.endsWith('/config')) result={controlled:!!state.controlled,recovery_scope:'a'.repeat(64),enabled:true,policy_id:'test-only',retention_seconds:300,
      identity:state.identity,assignments:{'echo-1':'v1'}};
    else if(url.endsWith('/conversations')) {
      const cid=body.request_id;
      state.attempts.set(cid,{messages:[],revision:0,turns:new Map()});
      result={conversation_id:cid,revision:0};
    } else if(url.includes('/conversations/')) {
      const cid=url.split('/conversations/')[1].split('/')[0],attempt=state.attempts.get(cid);
      if(!attempt) status=404;
      else if(options.method==='DELETE') {state.attempts.delete(cid);status=204;}
      else if(url.endsWith('/jobs')) {
        attempt.messages.push({request_id:body.request_id,role:'student',text:body.message,status:'completed'},{request_id:body.request_id,role:'assistant',text:state.reply||'Controlled answer',status:'completed'});
        attempt.revision+=2;
        state.savedResult={id:'b'.repeat(64),state:'completed',result:{message:state.reply||'Controlled answer',conversation_id:cid,revision:attempt.revision}};
        result={id:'b'.repeat(64),state:'queued'};
        if(state.loseReply) {state.loseReply=false;throw new Error('connection lost');}
      }
      else if(url.endsWith('/turns')) {
        if(!attempt.turns.has(body.request_id)) {
          attempt.messages.push({request_id:body.request_id,role:'student',text:body.message,status:'completed'},
            {request_id:body.request_id,role:'assistant',text:'Released answer',status:'completed'});
          attempt.revision+=2;
          attempt.turns.set(body.request_id,{revision:attempt.revision,response:{message:'Released answer'},
            live_signals:{affective_state:'curious',confidence:0.7,planner_note:'Offer a small check',
              self_critique:'Check assumptions',governance:'none',memory:{grasped:['grouping']},
              components:{self_eval:{leak_risk:'none'},timings_ms:{planner_ms:12}}}});
        }
        result=attempt.turns.get(body.request_id);
        if(state.loseReply) {state.loseReply=false;throw new Error('connection lost');}
      } else {
        if(state.failHistory) {state.failHistory=false;throw new Error('History connection lost');}
        result={messages:attempt.messages,revision:attempt.revision,pending:false,before:null};
      }
    } else if(url.endsWith('/api/sol/jobs')) result={message:state.reply||'Live answer',components:{},memory:{}};
    else if(url.endsWith('/api/run')) result=state.runResult||{ok:true,pack:{id:'datascience',stdout:'Done'}};
    else throw new Error('unexpected endpoint '+url);
    return {ok:status<400,status,headers:new Headers(),json:async()=>result};
  };
  const context=vm.createContext({window,document,fetch,URL,localStorage:window.localStorage,crypto:require("node:crypto").webcrypto,setTimeout,clearTimeout,AbortController,Headers});
  for(const file of ['auth-client.js','control-messages.js','request-lifecycle.js','ask-jobs.js','conversation-client.js','dev-client.js']) {
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
    if(file==='ask-jobs.js' && state.testPolling) {
      const factory=context.belayAskJobs;
      context.belayAskJobs=options=>factory({...options,wait:()=>new Promise(resolve=>{state.releasePoll=resolve;}),
        timeoutMs:state.timeoutMs||90000});
    }
  }
  for(let i=0;i<12;i++) await tick();
  const controls=()=>{
    const all=[]; function walk(e) {all.push(e);for(const c of e.children||[]) walk(c);}
    walk(nodes['conversation-controls']);
    return {check:all.find(e=>e.type==='checkbox'),button:text=>all.find(e=>e.tagName==='button'&&e.textContent===text)};
  };
  return {state,nodes,calls,window,controls,context};
}

test('unsaved current question reaches authenticated legacy edge and stays out of browser storage',async()=>{
  const env=await setup(); env.nodes.question.value='Explain my current question';
  await env.nodes.ask.fire('click');
  const request=env.calls.find(c=>c.url.endsWith('/api/sol/jobs'));
  const body=JSON.parse(request.options.body);
  assert.deepEqual(body.recent,[{who:'student',text:'Explain my current question'}]);
  assert.equal(body.participant_id,'gh:1');
  assert.match(env.nodes['chat-feed'].textContent,/Explain my current question/);
  for(const call of env.calls) assert.equal(call.options.headers.Authorization,'Bearer short-lived-token');
  assert.ok([...env.state.entries.values()].every(v=>!v.includes('Explain my current question')));
});

test('enrollment URL fixes the stance for saved and unsaved calls without a student toggle',async()=>{
  const env=await setup({search:'?stance=control'});env.nodes.question.value='Offline control check';
  await env.nodes.ask.fire('click');
  assert.equal(JSON.parse(env.calls.find(c=>c.url.endsWith('/api/sol/jobs')).options.body).stance,'control');
  const check=env.controls().check;check.checked=true;await check.fire('change');
  env.nodes.question.value='Saved control check';await env.nodes.ask.fire('click');
  assert.equal(JSON.parse(env.calls.find(c=>c.url.endsWith('/turns')).options.body).stance,'control');
});

test('saved bubbles restore after reload without resending client history or duplicating replies',async()=>{
  const first=await setup(),check=first.controls().check; check.checked=true;await check.fire('change');
  first.nodes.question.value='A saved question'; await first.nodes.ask.fire('click');
  const turn=first.calls.find(c=>c.url.endsWith('/turns')),body=JSON.parse(turn.options.body);
  assert.equal(body.message,'A saved question'); assert.equal(body.expected_revision,0);
  assert.equal(body.recent,undefined);
  assert.equal(bubbles(first).length,2);
  assert.match(first.nodes.planner.textContent,/Offer a small check/);
  assert.equal(first.nodes.conf.textContent,'70%');
  const restored=await setup(first.state);
  assert.equal(bubbles(restored).length,2);
  assert.match(restored.nodes['chat-feed'].textContent,/A saved question/);
  assert.equal(restored.calls.some(c=>c.url.endsWith('/turns')),false);
  assert.equal(restored.nodes.planner.textContent,'—');
  assert.equal(restored.nodes.conf.textContent,'—');
  assert.match(restored.nodes['signals-status'].textContent,/Saved replies restored/);
  assert.ok(!JSON.stringify([...first.state.entries]).includes('A saved question'));
  assert.ok(!JSON.stringify([...first.state.entries]).includes('short-lived-token'));
});

test('same-attempt refresh retains live signals in RAM; new attempt clears them',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.nodes.question.value='Explain grouping';await env.nodes.ask.fire('click');
  assert.equal(env.nodes.conf.textContent,'70%');
  await env.controls().button('Refresh history').fire('click');
  assert.equal(env.nodes.conf.textContent,'70%');
  assert.match(env.nodes.planner.textContent,/Offer a small check/);
  await env.controls().button('New conversation').fire('click');
  assert.equal(env.nodes.conf.textContent,'—');
  assert.doesNotMatch(env.nodes['signals-status'].textContent,/latest live reply/);
});

test('missing saved history after reload permits a new explicit attempt or unsaved tutoring',async()=>{
  const first=await setup(),check=first.controls().check;check.checked=true;await check.fire('change');
  first.nodes.question.value='Expired history';await first.nodes.ask.fire('click');
  first.state.attempts.clear();
  const restored=await setup(first.state);
  assert.doesNotMatch(restored.nodes['chat-feed'].textContent,/Expired history/);
  assert.equal(restored.state.attempts.size,0); // No silent replacement.
  await restored.controls().button('New conversation').fire('click');
  assert.equal(restored.state.attempts.size,1);
  restored.nodes.question.value='New saved question';await restored.nodes.ask.fire('click');
  assert.equal(bubbles(restored).length,2);
  restored.state.attempts.clear();
  const unsaved=await setup(restored.state),toggle=unsaved.controls().check;
  toggle.checked=false;await toggle.fire('change');
  unsaved.nodes.question.value='Still available';await unsaved.nodes.ask.fire('click');
  assert.ok(unsaved.calls.some(c=>c.url.endsWith('/api/sol/jobs')));
});

test('an unavailable attempt keeps an unrelated run result in an unchanged authorized scope',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.state.runResult={ok:false,pack:{id:'datascience',stdout:'Keep this result'}};
  await env.nodes.run.fire('click');
  env.state.attempts.clear();await env.controls().button('Refresh history').fire('click');
  assert.match(env.nodes.result.textContent,/Keep this result/);
  await env.controls().button('New conversation').fire('click');
  env.nodes.question.value='Continue';await env.nodes.ask.fire('click');
  assert.equal(bubbles(env).length,2);
});

test('lost saved reply retry reuses request ID and appends one exchange',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.nodes.question.value='Retry safely';env.state.loseReply=true;
  await env.nodes.ask.fire('click');assert.match(env.nodes.status.textContent,/connection was lost/);
  await env.nodes.ask.fire('click');
  const turns=env.calls.filter(c=>c.url.endsWith('/turns')).map(c=>JSON.parse(c.options.body));
  assert.equal(turns[0].request_id,turns[1].request_id);
  assert.equal(bubbles(env).length,2);
});

test('a history network failure after completion keeps the successful live Sol reply visible',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.state.failHistory=true;env.nodes.question.value='A completed question';await env.nodes.ask.fire('click');
  assert.equal(bubbles(env).length,2);
  assert.equal(bubbles(env)[1].innerHTML,'Released answer');
  assert.equal(env.nodes.conf.textContent,'70%');
  await env.controls().button('Refresh history').fire('click');
  assert.equal(bubbles(env).length,2);
});

test('new and delete attempt controls clear saved bubbles and preserve optional saving',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.nodes.question.value='Old attempt';await env.nodes.ask.fire('click');
  await env.controls().button('New conversation').fire('click');
  assert.equal(env.state.attempts.size,2);assert.doesNotMatch(env.nodes['chat-feed'].textContent,/Old attempt/);
  await env.controls().button('Delete saved attempt').fire('click');
  assert.equal(env.state.attempts.size,1);assert.equal(check.checked,true);
  assert.match(env.nodes['chat-feed'].textContent,/history will appear/);
});

test('silent identity change clears the old unsaved feed and refuses the previous input',async()=>{
  const env=await setup();env.nodes.question.value='Private old question';await env.nodes.ask.fire('click');
  env.state.identity={institution_id:'inst-b',class_id:'class-b',learner_id:'gh:2'};
  env.nodes.question.value='Typed before identity changed';await env.nodes.ask.fire('click');
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,1);
  assert.doesNotMatch(env.nodes['chat-feed'].textContent,/Private old question/);
  assert.match(env.nodes.status.textContent,/Identity changed/);
});

test('revoked credentials clear transient feed and do not call the tutor',async()=>{
  const env=await setup();env.nodes.question.value='Private question';await env.nodes.ask.fire('click');
  env.state.unauthorized=true;env.nodes.question.value='Another question';await env.nodes.ask.fire('click');
  assert.doesNotMatch(env.nodes['chat-feed'].textContent,/Private question/);
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,1);
});

test('a failed run does not ask the tutor; pack-agnostic output remains readable',async()=>{
  const env=await setup();env.state.runResult={ok:false,error:'Synthetic run failure'};
  await env.nodes.run.fire('click');
  assert.equal(env.calls.some(c=>c.url.endsWith('/api/sol/jobs')),false);
  assert.match(env.nodes.result.textContent,/Synthetic run failure/);
});

test('student ValueError submits its result once and displays tutor feedback',async()=>{
  const env=await setup();
  env.state.runResult={ok:false,error:'ValueError: wrong shape',pack:{execution_status:'student_error'}};
  await env.nodes.run.fire('click');
  const submissions=env.calls.filter(c=>c.url.endsWith('/api/sol/jobs'));
  assert.equal(submissions.length,1);
  assert.equal(JSON.parse(submissions[0].options.body).result.error,'ValueError: wrong shape');
  assert.match(bubbles(env).at(-1).innerHTML,/Live answer/);
  assert.match(env.nodes.result.textContent,/ValueError/);
});

test('sandbox timeout does not submit automatic model feedback',async()=>{
  const env=await setup();
  env.state.runResult={ok:false,error:'timeout',pack:{execution_status:'timeout',timed_out:true}};
  await env.nodes.run.fire('click');
  assert.equal(env.calls.some(c=>c.url.endsWith('/api/sol/jobs')),false);
  assert.match(env.nodes.status.textContent,/Code execution.*No tutor feedback/);
});

test('run results show printed values and check feedback without exposing the API envelope',async()=>{
  const env=await setup({search:'?stance=control'});
  env.state.runResult={ok:true,goalMet:false,metric:null,pack:{id:'datascience',stdout:'{A: 12}\n',
    checks:[{ok:false,detail:'Expected one value per category'}]}};
  await env.nodes.run.fire('click');
  assert.match(env.nodes.result.textContent,/\{A: 12\}/);
  assert.match(env.nodes.result.textContent,/Some exercise checks need attention/);
  assert.match(env.nodes.result.textContent,/Check details · 0\/1 passed/);
  assert.doesNotMatch(env.nodes.result.textContent,/"pack"|"goalMet"|"metric"/);
  const turn=env.calls.find(c=>c.url.endsWith('/api/sol/jobs'));
  assert.deepEqual(JSON.parse(turn.options.body).result,env.state.runResult); // Full context still goes to Sol.
  assert.equal(JSON.parse(turn.options.body).event,'run');
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/run')).length,1);
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,1);
  assert.match(bubbles(env).at(-1).innerHTML,/Live answer/);
});

test('Run succeeds but disabled feedback is a confirmed non-submission, with no request pointer or POST',async()=>{
 const env=await setup({jobsConfigCode:'jobs_disabled'});
 assert.doesNotMatch(env.nodes.status.textContent,/not confirmed|still be running/);
 await env.nodes.run.fire('click');
 assert.match(env.nodes.result.textContent,/Code ran successfully/);
 assert.match(env.nodes.status.textContent,/Code ran.*No new tutor feedback was submitted.*not enabled/);
 assert.equal(env.nodes.ask.textContent,'Ask Sol');
 assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,0);
 assert.equal([...env.state.entries.keys()].some(k=>k.startsWith('belay.ask.')),false);
});

test('Run keeps a prior unknown tutor request and does not submit feedback for the new run',async()=>{
 const env=await setup({unknown:true});await env.nodes.run.fire('click');
 const before=JSON.stringify([...env.state.entries]);
 await env.nodes.run.fire('click');
 assert.equal(env.calls.filter(c=>c.url.endsWith('/api/run')).length,2);
 assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,1);
 assert.equal(JSON.stringify([...env.state.entries]),before);
 assert.match(env.nodes.status.textContent,/previous tutor request.*no feedback for this run was submitted/);
 assert.equal(env.nodes.ask.textContent,'Check request status');
 assert.match(env.nodes.result.textContent,/Code ran successfully/);
});

test('empty output has a useful hint and runtime output stays literal text',async()=>{
  const env=await setup();env.state.runResult={ok:false,error:'<script>unsafe()</script>',pack:{stdout:''}};
  await env.nodes.run.fire('click');
  assert.match(env.nodes.result.textContent,/No printed output/);
  assert.equal(env.nodes.result.children.find(e=>e.className==='run-error').innerHTML,'');
});

test('without Markdown dependencies model text is escaped rather than inserted as executable HTML',async()=>{
  const env=await setup();env.state.reply='<script>unsafe()</script><img src=x onerror=unsafe()>';
  env.nodes.question.value='Test rendering';await env.nodes.ask.fire('click');
  const answer=bubbles(env)[1];
  assert.match(answer.innerHTML,/&lt;script&gt;/);assert.ok(!answer.innerHTML.includes('<script>'));
});


test('controlled saved UI restores a lost admission using GET and shows no invented signals',async()=>{
 const first=await setup({controlled:true}),check=first.controls().check;check.checked=true;await check.fire('change');
 first.nodes.question.value='Saved controlled question';first.state.loseReply=true;await first.nodes.ask.fire('click');
 assert.match(first.nodes.status.textContent,/connection was lost/);
 const restored=await setup(first.state);
 assert.equal(restored.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,0);
 assert.equal(bubbles(restored).length,2);
 assert.equal(restored.nodes.planner.textContent,'—');
 restored.nodes.question.value='Another';await restored.nodes.ask.fire('click');
 assert.equal(bubbles(restored).length,4);
});

test('controlled unknown UI keeps query-only pointer after refresh and changed input',async()=>{
 const first=await setup({controlled:true,unknown:true}),check=first.controls().check;check.checked=true;await check.fire('change');
 first.nodes.question.value='Unknown';await first.nodes.ask.fire('click');
 const restored=await setup(first.state);restored.nodes.question.value='Different';await restored.nodes.ask.fire('click');
 assert.equal(restored.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,0);
 assert.match(restored.nodes.status.textContent,/not confirmed/);
 assert.equal(restored.nodes.ask.disabled,false);
});

async function pollPaused(env) {
  for(let i=0;i<100 && !env.state.releasePoll;i++) await tick();
  assert.equal(typeof env.state.releasePoll,'function','mock poll reached its waiting point');
}
function releasePoll(env) {
  const release=env.state.releasePoll; env.state.releasePoll=null; release();
}
function assertWaiting(env,label) {
  assert.equal(env.nodes['chat-feed']['aria-busy'],'true');
  assert.equal(env.nodes['feedback-loading'].hidden,false);
  assert.equal(env.nodes.ask.disabled,true); assert.equal(env.nodes.run.disabled,true);
  assert.equal(env.nodes.ask.textContent,label);
  assert.equal(env.nodes.status.textContent,'');
  assert.match(env.nodes['feedback-announcement'].textContent,/Preparing tutor feedback/);
  assert.doesNotMatch(env.nodes['conversation-controls'].textContent,/Checking request status|Waiting for a worker|Sol is working/);
}

for(const saved of [false,true]) for(const terminal of ['completed','failed','unknown']) {
  test(`${saved?'saved':'unsaved'} queued → running → ${terminal}: silent visual wait and accessible busy state`,async()=>{
    const env=await setup({controlled:true,testPolling:true,pollStates:['queued','running'],
      pollTerminal:terminal==='completed'?null:terminal});
    if(saved) {const check=env.controls().check;check.checked=true;await check.fire('change');}
    const pending=env.nodes.ask.fire('click');
    await pollPaused(env);assertWaiting(env,'Ask Sol');
    const announcement=env.nodes['feedback-announcement'].textContent;
    await env.nodes.run.fire('click'); // blocked; not a second execution
    releasePoll(env);await pollPaused(env);assertWaiting(env,'Ask Sol');
    assert.equal(env.nodes['feedback-announcement'].textContent,announcement);
    releasePoll(env);await pending;
    assert.equal(env.nodes['feedback-loading'].hidden,true);
    assert.equal(env.nodes['chat-feed']['aria-busy'],'false');
    assert.equal(env.nodes.ask.disabled,false);assert.equal(env.nodes.run.disabled,false);
    assert.equal(env.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,1);
    assert.equal(env.calls.filter(c=>c.url.endsWith('/api/run')).length,0);
    if(terminal==='completed') {
      assert.equal(env.nodes.status.textContent,'');
      assert.match(bubbles(env).at(-1).innerHTML,/answer/);
    } else if(terminal==='unknown') {
      assert.match(env.nodes.status.textContent,/not confirmed/);
      assert.equal(env.nodes.ask.textContent,'Check request status');
      const pointers=JSON.stringify([...env.state.entries]);
      await env.nodes.ask.fire('click');
      assert.equal(JSON.stringify([...env.state.entries]),pointers);
      assert.equal(env.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,1);
    } else {
      assert.ok(env.nodes.status.textContent.length>0);
      assert.equal(env.nodes.ask.textContent,'Ask Sol');
    }
  });
}

test('long polling timeout ends animation with a query-only recovery entry and stable request ID',async()=>{
  const env=await setup({testPolling:true,timeoutMs:30,pollStates:['running']});
  const pending=env.nodes.ask.fire('click');await pollPaused(env);
  const pointers=JSON.stringify([...env.state.entries]);assertWaiting(env,'Ask Sol');
  await new Promise(resolve=>setTimeout(resolve,40));releasePoll(env);await pending;
  assert.equal(env.nodes['feedback-loading'].hidden,true);
  assert.equal(env.nodes.ask.disabled,false);
  assert.equal(env.nodes.ask.textContent,'Check request status');
  assert.match(env.nodes.status.textContent,/not confirmed|timed out/);
  assert.equal(JSON.stringify([...env.state.entries]),pointers);
  assert.equal(env.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,1);
});

test('saved and unsaved refresh recovery show the same silent busy state without submitting again',async()=>{
  for(const saved of [false,true]) {
    const first=await setup({controlled:true,unknown:true});
    if(saved) {const check=first.controls().check;check.checked=true;await check.fire('change');}
    await first.nodes.ask.fire('click');
    first.state.unknown=false;first.state.testPolling=true;first.state.pollStates=['queued','running'];
    const restored=await setup(first.state);await pollPaused(restored);assertWaiting(restored,'Ask Sol');
    releasePoll(restored);await pollPaused(restored);assertWaiting(restored,'Ask Sol');
    releasePoll(restored);for(let i=0;i<20;i++) await tick();
    assert.equal(restored.nodes['feedback-loading'].hidden,true);
    assert.equal(restored.nodes.ask.disabled,false);
    assert.equal(restored.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,0);
    assert.match(bubbles(restored).at(-1).innerHTML,/answer/);
  }
});

const markdownFixture='**Bold feedback**\n\n- First item\n- Second with `total`\n\n1. Numbered item\n\n```python\ndef check(x):\n    return "<script>literal code</script>"\n```\n\n[Safe link](https://example.org) [Unsafe](javascript:alert(1))\n\n'+
  '<img src=x onerror="alert(1)"><script>alert(1)</script><svg onload="alert(1)"></svg><style>body{display:none}</style>';

async function renderedPaths(reply) {
  const first=await setup({withMarkdown:true,controlled:true,reply});
  await first.nodes.ask.fire('click');
  const answer=env=>env.nodes['chat-feed'].querySelector('.bubble-tutor');
  const outputs=[answer(first)];
  // Unknown admission pointer → GET-only task recovery, never another model dispatch.
  const unknown=await setup({withMarkdown:true,controlled:true,reply,unknown:true});
  await unknown.nodes.ask.fire('click');unknown.state.unknown=false;
  const recovered=await setup(unknown.state);outputs.push(answer(recovered));
  assert.equal(recovered.calls.filter(c=>c.options.method==='POST').length,0);
  // Saved response → restored conversation history.
  const saved=await setup({withMarkdown:true,controlled:true,reply});
  const check=saved.controls().check;check.checked=true;await check.fire('change');
  await saved.nodes.ask.fire('click');outputs.push(answer(saved));
  const history=await setup(saved.state);outputs.push(answer(history));
  assert.equal(history.calls.filter(c=>c.options.method==='POST').length,0);
  // Lost saved admission → saved task result + authorized history restoration.
  saved.state.unknown=true;await saved.nodes.ask.fire('click');saved.state.unknown=false;
  const savedRecovered=await setup(saved.state);outputs.push(answer(savedRecovered));
  assert.equal(savedRecovered.calls.filter(c=>c.options.method==='POST').length,0);
  return outputs;
}

test('actual Marked / DOMPurify / Highlight.js preserve Markdown safely across live and both recovery paths',async()=>{
  const outputs=await renderedPaths(markdownFixture);
  for(const answer of outputs) {
    assert.ok(answer,'nonempty tutor bubble');
    assert.equal(answer.querySelector('strong').textContent,'Bold feedback');
    assert.equal(answer.querySelectorAll('ul li').length,2);
    assert.equal(answer.querySelectorAll('ol li').length,1);
    assert.equal(answer.querySelector('li code').textContent,'total');
    assert.match(answer.querySelector('pre code').textContent,/<script>literal code<\/script>/);
    assert.ok(answer.querySelector('pre code .hljs-keyword'));
    assert.equal(answer.querySelectorAll('script,style,svg,iframe,[onerror],[onload]').length,0);
    const links=[...answer.querySelectorAll('a')];
    assert.equal(links[0].getAttribute('href'),'https://example.org');
    assert.equal(links[0].getAttribute('rel'),'noopener noreferrer');
    assert.equal(links[1].hasAttribute('href'),false);
    assert.equal(answer.innerHTML,outputs[0].innerHTML);
  }
});

test('plain model text stays plain and consistent across new reply and recovery; no invented emphasis',async()=>{
  const text='A plain tutor answer. No formatting was requested.';
  for(const answer of await renderedPaths(text)) {
    assert.equal(answer.textContent.trim(),text);
    assert.equal(answer.querySelectorAll('strong,li,code').length,0);
  }
});

test('unsafe links / HTML and unknown fenced languages stay safe; dependency fallback is literal',async()=>{
  const env=await setup({withMarkdown:true});
  env.state.reply='[Data](data:text/html;base64,PHNjcmlwdD4=) [File](file:///secret)'+
    ' <a href="javascript&#58;alert(1)" onclick="alert(1)">bad</a>\n\n```unregistered\n<img onerror=alert(1)>\n```';
  await env.nodes.ask.fire('click');
  let answer=env.nodes['chat-feed'].querySelector('.bubble-tutor');
  assert.equal(answer.querySelectorAll('a[href], [onclick], [onerror]').length,0);
  assert.equal(answer.querySelector('pre code').textContent.trim(),'<img onerror=alert(1)>');
  env.window.DOMPurify=null;env.state.reply='**literal**\n<script>alert(1)</script>';
  await env.nodes.ask.fire('click');answer=env.nodes['chat-feed'].querySelectorAll('.bubble-tutor')[1];
  assert.equal(answer.querySelectorAll('script,strong').length,0);
  assert.equal(answer.textContent,env.state.reply);
  assert.ok(answer.classList.contains('markdown-plain'));
});

test('pinned browser assets match installed sources and dev-client loads them locally',()=>{
  const files=[['marked.umd.js','marked/lib/marked.umd.js'],['purify.min.js','dompurify/dist/purify.min.js'],
    ['highlight.min.js','@highlightjs/cdn-assets/highlight.min.js']];
  const html=fs.readFileSync(path.join(root,'dev-client.html'),'utf8');
  for(const [vendor,source] of files) {
    assert.deepEqual(fs.readFileSync(path.join(root,'vendor',vendor)),fs.readFileSync(path.join(root,'node_modules',source)));
    assert.ok(html.includes(`src="vendor/${vendor}"`));
  }
});

test('page exposes nonvisual loading and reduced-motion styling without visible waiting prose',()=>{
  const {JSDOM}=require('jsdom');
  const html=fs.readFileSync(path.join(root,'dev-client.html'),'utf8');
  const doc=new JSDOM(html).window.document;
  assert.equal(doc.getElementById('chat-feed').getAttribute('aria-busy'),'false');
  const spinner=doc.getElementById('feedback-loading');
  assert.equal(spinner.hidden,true);assert.equal(spinner.getAttribute('aria-hidden'),'true');
  const announcement=doc.getElementById('feedback-announcement');
  assert.equal(announcement.getAttribute('role'),'status');
  assert.ok(announcement.classList.contains('sr-only'));
  assert.match(html,/prefers-reduced-motion: reduce/);
  assert.match(html,/\.sr-only\s*\{[^}]*clip-path: inset\(50%\)/);
});

const elements=env=>{
 const out=[];const walk=e=>{out.push(e);for(const c of e.children||[])walk(c);};walk(env.nodes['chat-feed']);return out;
};
const groups=env=>elements(env).filter(e=>e.className==='request-record');
const groupText=group=>{
 const texts=[];const walk=e=>{texts.push(e.text||e.innerHTML||'');for(const c of e.children||[])walk(c);};walk(group);return texts.join(' ');
};

test('old answer stays historical when SyntaxError feedback is budget blocked; next action archives that status',async()=>{
 const env=await setup();env.nodes.question.value='Earlier question';await env.nodes.ask.fire('click');
 const original=groups(env)[0]['data-request-id'];
 env.state.pollTerminal='failed';env.state.pollReason='budget_exhausted';env.state.runResult={ok:false,error:'SyntaxError: invalid syntax',pack:{execution_status:'student_error'}};
 await env.nodes.run.fire('click');
 assert.equal(groups(env).length,2);
 assert.equal(groups(env)[0]['data-request-id'],original);
 assert.match(groupText(groups(env)[0]),/Live answer/);
 assert.doesNotMatch(groupText(groups(env)[1]),/Live answer/);
 assert.doesNotMatch(groupText(groups(env)[1]),/SyntaxError/);
 assert.match(env.nodes.result.textContent,/SyntaxError/);
 assert.match(groupText(groups(env)[1]),/usage limit has been reached/);
 assert.ok(elements(env).some(e=>e.className==='history-boundary'));
 env.state.pollTerminal=null;env.nodes.question.value='Next question';await env.nodes.ask.fire('click');
 assert.equal(groups(env).length,3);
 assert.doesNotMatch(groupText(groups(env)[1]),/SyntaxError/);
 assert.match(env.nodes.result.textContent,/SyntaxError/);
 assert.match(groupText(groups(env)[2]),/Live answer/);
});

test('unknown original request is recovered into its original group without claiming new input was submitted',async()=>{
 const env=await setup({unknown:true});env.nodes.question.value='Original';await env.nodes.ask.fire('click');
 const id=groups(env)[0]['data-request-id'];
 assert.match(groupText(groups(env)[0]),/not confirmed/);
 env.state.unknown=false;env.nodes.question.value='New input';await env.nodes.ask.fire('click');
 assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/jobs')).length,1);
 assert.equal(groups(env).filter(g=>g['data-request-id']===id).length,1);
 assert.match(groupText(groups(env)[0]),/Live answer/);
 assert.doesNotMatch(groupText(groups(env).at(-1)),/Live answer/);
 assert.match(groupText(groups(env).at(-1)),/No new feedback submitted/);
});

test('saved history retains stable request grouping across refresh and repeated restore',async()=>{
 const env=await setup({controlled:true});const check=env.controls().check;check.checked=true;await check.fire('change');
 env.nodes.question.value='Saved request';await env.nodes.ask.fire('click');
 const id=groups(env)[0]['data-request-id'];
 const restored=await setup(env.state);
 await restored.controls().button('Refresh history').fire('click');
 assert.equal(groups(restored).filter(g=>g['data-request-id']===id).length,1);
 assert.equal(bubbles(restored).filter(b=>b.className.includes('bubble-tutor')).length,1);
 assert.equal(restored.calls.some(c=>c.options.method==='POST'),false);
 assert.doesNotMatch(groupText(groups(restored)[0]),/Request |Submitted code|Execution details/);
});

test('refresh restores unknown status and later result only in the original request group',async()=>{
 const first=await setup({unknown:true});first.nodes.question.value='Original';await first.nodes.ask.fire('click');
 const id=groups(first)[0]['data-request-id'];
 const restored=await setup(first.state);
 assert.equal(groups(restored)[0]['data-request-id'],id);
 assert.match(groupText(groups(restored)[0]),/not confirmed/);
 assert.equal(restored.calls.some(c=>c.options.method==='POST'),false);
 restored.state.unknown=false;const recovered=await setup(restored.state);
 assert.equal(groups(recovered).length,1);assert.equal(groups(recovered)[0]['data-request-id'],id);
 assert.match(groupText(groups(recovered)[0]),/Live answer/);
 assert.equal(recovered.calls.some(c=>c.options.method==='POST'),false);
});

test('expired temporary result is an operation notice, not an assistant reply',async()=>{
 const env=await setup({pollTerminal:'result_expired',pollReason:'result_expired'});
 env.nodes.question.value='Test expiry';await env.nodes.ask.fire('click');
 assert.equal(bubbles(env).filter(b=>b.className.includes('bubble-tutor')).length,0);
 assert.match(groupText(groups(env)[0]),/This response can no longer be restored/);
 assert.match(groupText(groups(env)[0]),/enter a question and choose Ask Sol/);
 assert.doesNotMatch(groupText(groups(env)[0]),/Tutor feedback:/);
 assert.equal(groups(env)[0]['data-feedback-state'],'result_expired');
});

test('expiry notice needs a confirmed result lookup and recovery never submits a replacement',async()=>{
 const first=await setup({withMarkdown:true,pollTerminal:'result_expired',pollReason:'result_expired'});
 assert.doesNotMatch(first.nodes['chat-feed'].textContent,/can no longer be restored/);
 assert.equal(first.calls.some(c=>c.url.includes('/by-request/')),false);
 first.nodes.question.value='Question whose result expires';await first.nodes.ask.fire('click');
 const id=first.nodes['chat-feed'].querySelector('.request-record').getAttribute('data-request-id');
 const restored=await setup(first.state);
 const feed=restored.nodes['chat-feed'];
 assert.equal(feed.querySelectorAll('.feedback-state').length,1);
 assert.equal(feed.querySelector('.feedback-state').getAttribute('role'),'note');
 assert.equal(feed.querySelector('.feedback-state').getAttribute('aria-label'),'System notice');
 assert.equal(feed.querySelector('.request-record').getAttribute('data-request-id'),id);
 assert.match(feed.textContent,/This response can no longer be restored/);
 assert.equal(feed.querySelectorAll('.bubble-tutor').length,0);
 assert.equal(restored.calls.some(c=>c.options.method==='POST'),false);
 assert.equal(restored.calls.filter(c=>c.url.includes('/by-request/')).length,1);
 assert.equal(restored.nodes.ask.disabled,false);
 // A replacement is created only after the learner chooses Ask Sol.
 restored.state.pollTerminal=null;restored.nodes.question.value='New question';
 await restored.nodes.ask.fire('click');
 assert.equal(restored.calls.filter(c=>c.options.method==='POST'&&c.url.endsWith('/jobs')).length,1);
 assert.equal(feed.querySelectorAll('.request-record').length,2);
 assert.equal(feed.querySelectorAll('.bubble-tutor').length,1);
 assert.equal((feed.textContent.match(/This response can no longer be restored/g)||[]).length,1);
});

test('only newest completed reply owns a collapsed inline Glass Box; new round removes old signals',async()=>{
 const env=await setup({withMarkdown:true,reply:'**Prior answer** with `result`.'});
 env.nodes.question.value='First question';await env.nodes.ask.fire('click');
 const box=env.nodes['glass-box'],feed=env.nodes['chat-feed'];
 assert.equal(box.open,false);assert.ok(feed.contains(box));
 assert.match(box.parentElement.textContent,/Prior answer/);
 box.open=true;
 env.state.testPolling=true; // immediate failure still archives prior answer and removes signals
 env.state.pollTerminal='failed';env.state.pollReason='budget_exhausted';
 env.nodes.question.value='Second question';await env.nodes.ask.fire('click');
 assert.ok(!feed.contains(box));assert.equal(box.open,false);
 assert.match(feed.textContent,/Prior answer/);assert.match(feed.textContent,/usage limit/);
 assert.equal(feed.querySelectorAll('.bubble-tutor').length,1);
 env.state.pollTerminal=null;env.state.reply='**New answer**\n\n```python\nprint(result)\n```';
 env.nodes.question.value='Third question';await env.nodes.ask.fire('click');
 assert.ok(feed.contains(box));assert.equal(box.open,false);
 assert.match(box.parentElement.textContent,/New answer/);
 assert.equal(feed.querySelectorAll('#glass-box').length,1);
 assert.ok(feed.querySelector('pre code .hljs-built_in'));
 assert.equal(feed.querySelectorAll('strong').length,2);
 assert.doesNotMatch(feed.textContent,/Submitted code|Request UUID|Checking request status/);
});


test('desktop columns share equal width and bounded height; workspace corners are compact',()=>{
 const html=fs.readFileSync(path.join(root,'dev-client.html'),'utf8');
 assert.match(html,/--right-col: minmax\(0, 1fr\)/);
 assert.match(html,/--radius-card: 8px/);
 assert.match(html,/\.request-record \.bubble \{[^}]*border-radius: 6px/);
 assert.match(html,/\.conversation-card \.chat-feed \{ border-radius: 6px/);
 assert.match(html,/main \{ min-height: calc\(100dvh - 48px\)/);
 assert.match(html,/\.col-right \{ contain: size; min-height: 0/);
 assert.doesNotMatch(html,/@media \(min-width: 900px\) and \(min-height:/);
 assert.match(html,/\.conversation-card \{ flex: 1; min-height: 0; overflow: hidden/);
});
