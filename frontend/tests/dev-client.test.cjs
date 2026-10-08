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
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function setup(state={}) {
  state.entries ||= new Map(); state.attempts ||= new Map(); state.serial ||= 0;
  state.identity ||= {institution_id:'inst-a',class_id:'class-a',learner_id:'gh:1'};
  const calls=[],nodes={},handlers={};
  for(const id of ['backend','exercise','mode','source','question','status','result','prompt','chat-feed',
    'conversation-controls','ask','run','affect','interv','planner','selfeval','gov','mem','timings','conf','confbar','signals-status']) {
    nodes[id]=new Element(id==='exercise'?'select':'div');
  }
  nodes.backend.value='https://belay.invalid'; nodes.mode.value='study';
  const window={location:{href:'https://host.invalid'+(state.search||'')},BELAY_AUTH_ORIGIN:'https://belay.invalid',
    BELAY_GET_ACCESS_TOKEN:async()=>'short-lived-token',BELAY_LEARNER_ID:'gh:1',
    BELAY_INSTITUTION_ID:'inst-a',BELAY_CLASS_ID:'class-a',crypto:{randomUUID:()=>`request-${++state.serial}`},
    addEventListener:(event,handler)=>handlers[event]=handler,
    localStorage:{getItem:key=>state.entries.get(key)||null,setItem:(key,value)=>state.entries.set(key,value)}};
  const document={getElementById:id=>nodes[id],createElement:tag=>new Element(tag),
    createTextNode:text=>({textContent:text})};
  const fetch=async(url,options)=>{
    calls.push({url,options});
    if(state.unauthorized) return {ok:false,status:401,json:async()=>({detail:'invalid credentials'})};
    const body=options.body?JSON.parse(options.body):{};
    let result={},status=200;
    if(url.endsWith('/api/curriculum')) result={modules:[{exercises:[{id:'echo-1',title:'Echo',prompt:'Learn loops',starter:'print(1)'}]}]};
    else if(url.endsWith('/config')) result={enabled:true,policy_id:'test-only',retention_seconds:300,
      identity:state.identity,assignments:{'echo-1':'v1'}};
    else if(url.endsWith('/conversations')) {
      const cid=body.request_id;
      state.attempts.set(cid,{messages:[],revision:0,turns:new Map()});
      result={conversation_id:cid,revision:0};
    } else if(url.includes('/conversations/')) {
      const cid=url.split('/conversations/')[1].split('/')[0],attempt=state.attempts.get(cid);
      if(!attempt) status=404;
      else if(options.method==='DELETE') {state.attempts.delete(cid);status=204;}
      else if(url.endsWith('/turns')) {
        if(!attempt.turns.has(body.request_id)) {
          attempt.messages.push({role:'student',text:body.message,status:'completed'},
            {role:'assistant',text:'Released answer',status:'completed'});
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
    } else if(url.endsWith('/api/sol/turn')) result={message:state.reply||'Live answer',components:{},memory:{}};
    else if(url.endsWith('/api/run')) result=state.runResult||{ok:true,pack:{id:'datascience',stdout:'Done'}};
    else throw new Error('unexpected endpoint '+url);
    return {ok:status<400,status,json:async()=>result};
  };
  const context=vm.createContext({window,document,fetch,URL});
  for(const file of ['auth-client.js','conversation-client.js','dev-client.js']) {
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
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
  const request=env.calls.find(c=>c.url.endsWith('/api/sol/turn'));
  const body=JSON.parse(request.options.body);
  assert.deepEqual(body.recent,[{who:'student',text:'Explain my current question'}]);
  assert.equal(body.participant_id,'gh:1'); assert.equal(body.class_id,'class-a');
  assert.match(env.nodes['chat-feed'].textContent,/Explain my current question/);
  for(const call of env.calls) assert.equal(call.options.headers.Authorization,'Bearer short-lived-token');
  assert.equal(env.state.entries.size,0);
});

test('enrollment URL fixes the stance for saved and unsaved calls without a student toggle',async()=>{
  const env=await setup({search:'?stance=control'});env.nodes.question.value='Offline control check';
  await env.nodes.ask.fire('click');
  assert.equal(JSON.parse(env.calls.find(c=>c.url.endsWith('/api/sol/turn')).options.body).stance,'control');
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
  assert.equal(first.nodes['chat-feed'].children.length,2);
  assert.match(first.nodes.planner.textContent,/Offer a small check/);
  assert.equal(first.nodes.conf.textContent,'70%');
  const restored=await setup(first.state);
  assert.equal(restored.nodes['chat-feed'].children.length,2);
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
  assert.equal(restored.nodes['chat-feed'].children.length,2);
  restored.state.attempts.clear();
  const unsaved=await setup(restored.state),toggle=unsaved.controls().check;
  toggle.checked=false;await toggle.fire('change');
  unsaved.nodes.question.value='Still available';await unsaved.nodes.ask.fire('click');
  assert.ok(unsaved.calls.some(c=>c.url.endsWith('/api/sol/turn')));
});

test('an unavailable attempt keeps an unrelated run result in an unchanged authorized scope',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.state.runResult={ok:false,pack:{id:'datascience',stdout:'Keep this result'}};
  await env.nodes.run.fire('click');
  env.state.attempts.clear();await env.controls().button('Refresh history').fire('click');
  assert.match(env.nodes.result.textContent,/Keep this result/);
  await env.controls().button('New conversation').fire('click');
  env.nodes.question.value='Continue';await env.nodes.ask.fire('click');
  assert.equal(env.nodes['chat-feed'].children.length,2);
});

test('lost saved reply retry reuses request ID and appends one exchange',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.nodes.question.value='Retry safely';env.state.loseReply=true;
  await env.nodes.ask.fire('click');assert.match(env.nodes.status.textContent,/connection lost/);
  await env.nodes.ask.fire('click');
  const turns=env.calls.filter(c=>c.url.endsWith('/turns')).map(c=>JSON.parse(c.options.body));
  assert.equal(turns[0].request_id,turns[1].request_id);
  assert.equal(env.nodes['chat-feed'].children.length,2);
});

test('a history network failure after completion keeps the successful live Sol reply visible',async()=>{
  const env=await setup(),check=env.controls().check;check.checked=true;await check.fire('change');
  env.state.failHistory=true;env.nodes.question.value='A completed question';await env.nodes.ask.fire('click');
  assert.equal(env.nodes['chat-feed'].children.length,2);
  assert.equal(env.nodes['chat-feed'].children[1].innerHTML,'Released answer');
  assert.equal(env.nodes.conf.textContent,'70%');
  await env.controls().button('Refresh history').fire('click');
  assert.equal(env.nodes['chat-feed'].children.length,2);
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
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/turn')).length,1);
  assert.doesNotMatch(env.nodes['chat-feed'].textContent,/Private old question/);
  assert.match(env.nodes.status.textContent,/Identity changed/);
});

test('revoked credentials clear transient feed and do not call the tutor',async()=>{
  const env=await setup();env.nodes.question.value='Private question';await env.nodes.ask.fire('click');
  env.state.unauthorized=true;env.nodes.question.value='Another question';await env.nodes.ask.fire('click');
  assert.doesNotMatch(env.nodes['chat-feed'].textContent,/Private question/);
  assert.equal(env.calls.filter(c=>c.url.endsWith('/api/sol/turn')).length,1);
});

test('a failed run does not ask the tutor; pack-agnostic output remains readable',async()=>{
  const env=await setup();env.state.runResult={ok:false,error:'Synthetic run failure'};
  await env.nodes.run.fire('click');
  assert.equal(env.calls.some(c=>c.url.endsWith('/api/sol/turn')),false);
  assert.match(env.nodes.result.textContent,/Synthetic run failure/);
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
  const turn=env.calls.find(c=>c.url.endsWith('/api/sol/turn'));
  assert.deepEqual(JSON.parse(turn.options.body).result,env.state.runResult); // Full context still goes to Sol.
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
  const answer=env.nodes['chat-feed'].children[1];
  assert.match(answer.innerHTML,/&lt;script&gt;/);assert.ok(!answer.innerHTML.includes('<script>'));
});
