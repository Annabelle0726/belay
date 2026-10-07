// SPDX-License-Identifier: AGPL-3.0-only
// Hermetic refresh/retry tests; no browser, identity server or model endpoint.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {test} = require('node:test');

function setup() {
  const entries = new Map(), calls = [], attempts = new Map();
  let subject = 'gh:1', serial = 0, unavailable = false, loseReply = false;
  const window = {location:{href:'https://host.invalid'}, BELAY_AUTH_ORIGIN:'https://belay.invalid',
    BELAY_GET_ACCESS_TOKEN:async()=>'short-token', BELAY_INSTITUTION_ID:'inst-a', BELAY_CLASS_ID:'class-a',
    crypto:{randomUUID:()=>`request-${++serial}`}, localStorage:{
      getItem:key=>entries.get(key) || null, setItem:(key,value)=>entries.set(key,value)}};
  const fetch = async (url, options) => {
    calls.push({url,options});
    let value = {}, status = 200;
    if (url.endsWith('/config')) value = {enabled:true, policy_id:'approved-test',retention_seconds:300,
      identity:{institution_id:'inst-a',class_id:'class-a',learner_id:subject},assignments:{'echo-1':'v1'}};
    else if (options.method === 'POST' && url.endsWith('/conversations')) {
      const body = JSON.parse(options.body);
      const cid = body.request_id;
      if (!attempts.has(cid)) attempts.set(cid,{revision:0,messages:[],turns:new Map()});
      value = {conversation_id:cid,revision:attempts.get(cid).revision};
    } else {
      const suffix = url.split('/conversations/')[1], cid = suffix.split('/')[0];
      const attempt = attempts.get(cid);
      if (unavailable || !attempt) status = 404;
      else if (options.method === 'DELETE') { attempts.delete(cid); status = 204; }
      else if (suffix.includes('/turns')) {
        const body = JSON.parse(options.body);
        value = attempt.turns.get(body.request_id);
        if (!value) {
          value = {revision:attempt.revision+2,response:{message:'Released answer',check_question:null}};
          attempt.turns.set(body.request_id,value); attempt.revision+=2;
          attempt.messages.push({sequence:attempt.revision-1,role:'student',text:body.message,status:'completed'},
                                {sequence:attempt.revision,role:'assistant',text:'Released answer',status:'completed'});
        }
        if (loseReply) { loseReply=false; throw new Error('connection lost'); }
      } else if (suffix.includes('before=')) value = {revision:attempt.revision,messages:[{sequence:0,role:'student',text:'older',status:'completed'}],before:null};
      else value = {revision:attempt.revision,messages:attempt.messages.slice(-2),before:attempt.messages.length>2?'scoped-cursor':null,pending:false};
    }
    return {ok:status<400,status,json:async()=>value};
  };
  const ctx = vm.createContext({window,URL,fetch});
  for (const file of ['auth-client.js','conversation-client.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),ctx);
  const make = () => new window.BelayConversations.Session({base:'https://belay.invalid',exercise:'echo-1'});
  return {make,entries,calls,attempts,setSubject:value=>subject=value,setUnavailable:value=>unavailable=value,
    loseReply:()=>loseReply=true};
}

test('refresh restores same authorized attempt; new attempt has separate history', async()=>{
  const env=setup(), first=env.make();
  await first.initialize(); assert.equal(first.enabled,false);
  await first.setSaving(true); const cid=first.cid;
  await first.send({message:'first'});
  const refreshed=env.make(); await refreshed.initialize();
  assert.equal(refreshed.cid,cid); assert.equal(refreshed.messages.length,2);
  await refreshed.newAttempt(); assert.notEqual(refreshed.cid,cid); assert.equal(refreshed.messages.length,0);
  for (const [key,value] of env.entries) {
    assert.ok(!key.includes('short-token')); assert.ok(!value.includes('first') && !value.includes('Released answer') && !value.includes('short-token'));
  }
  for (const call of env.calls) {
    assert.equal(call.options.headers.Authorization,'Bearer short-token');
    assert.ok(!call.url.includes('short-token'));
  }
});

test('lost response retry keeps request ID and cannot invent history', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  env.loseReply(); await assert.rejects(session.send({message:'hello'}),/connection lost/);
  const saved=await session.send({message:'hello'}); assert.equal(saved.message,'Released answer');
  const turns=env.calls.filter(c=>c.url.endsWith('/turns'));
  assert.equal(JSON.parse(turns[0].options.body).request_id,JSON.parse(turns[1].options.body).request_id);
  assert.equal(env.attempts.get(session.cid).messages.length,2);
  assert.ok(!('recent' in JSON.parse(turns[0].options.body)));
});

test('older history is paginated and unavailable history clears the pointer', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  await session.send({message:'first'}); await session.send({message:'second'});
  assert.equal(session.messages.length,2); await session.older(); assert.equal(session.messages[0].text,'older');
  env.setUnavailable(true); await assert.rejects(session.restore(),/unavailable, expired or deleted/);
  assert.equal(session.cid,null); assert.equal(session.messages.length,0);
  assert.ok(!JSON.parse(env.entries.get(session.key)).cid);
});

test('identity changes discard old transcript and saving preferences', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  await session.send({message:'private to first'}); const oldKey=session.key;
  env.setSubject('gh:2'); await session.restore();
  assert.notEqual(session.key,oldKey); assert.equal(session.messages.length,0); assert.equal(session.enabled,false);
});

test('delete removes current saved attempt without silently creating another', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  const cid=session.cid; await session.send({message:'hello'}); await session.remove();
  assert.equal(env.attempts.has(cid),false); assert.equal(session.cid,null);
  await assert.rejects(session.send({message:'new'}),/Choose a saved attempt/);
});

test('all three demos mount the shared restoration controls without styling changes',()=>{
  for (const file of ['widget.html','dev-client.html','embed-demo.html']) {
    const source=fs.readFileSync(path.join(__dirname,'..',file),'utf8');
    assert.match(source,/src="conversation-client\.js"/); assert.match(source,/BelayConversations\.mount/);
    assert.match(source,/dialogue\.send/);
    const scripts=[...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
    for (const [,script] of scripts) new vm.Script(script);
  }
});

test('refresh after a lost completed reply allows a new message', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  env.loseReply(); await assert.rejects(session.send({message:'first'}),/connection lost/);
  await session.restore();
  await session.send({message:'second'});
  assert.equal(env.attempts.get(session.cid).messages.length,4);
});

test('turning optional saving off still permits deletion of the saved pointer', async()=>{
  const env=setup(), first=env.make(); await first.initialize(); await first.setSaving(true);
  const cid=first.cid; await first.send({message:'hello'}); await first.setSaving(false);
  const refreshed=env.make(); await refreshed.initialize();
  assert.equal(refreshed.enabled,false); assert.equal(refreshed.cid,cid); assert.equal(refreshed.messages.length,0);
  await refreshed.remove(); assert.equal(env.attempts.has(cid),false);
});

test('a changed authenticated namespace cannot submit the previous learner message', async()=>{
  const env=setup(), session=env.make(); await session.initialize(); await session.setSaving(true);
  env.setSubject('gh:2');
  await assert.rejects(session.send({message:'previous learner text'}),/Identity changed/);
  assert.equal(env.calls.filter(call=>call.url.endsWith('/turns')).length,0);
  assert.equal(session.messages.length,0);
});
