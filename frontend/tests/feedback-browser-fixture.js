/* SPDX-License-Identifier: AGPL-3.0-only */
// Fixed, isolated browser data. NEVER delegate an unmatched request to real fetch.
(() => {
 const base='https://fixture.invalid', scope='f'.repeat(64), storage=new Map();
 Object.defineProperty(window,'localStorage',{value:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
 Object.assign(window,{BELAY_AUTH_ORIGIN:base,SOL_BACKEND_URL:base,BELAY_LEARNER_ID:'fixture-student',
  BELAY_INSTITUTION_ID:'fixture-school',BELAY_CLASS_ID:'fixture-class',BELAY_GET_ACCESS_TOKEN:async()=>'offline-test-only'});
 const jobs=new Map(),conversations=new Map(); let serial=0;
 window.fixtureRequests=[];
 const identity={institution_id:'fixture-school',class_id:'fixture-class',learner_id:'fixture-student'};
 const assignments={'ds-foundations':'v1','ds-regression':'v1','ds-mlp':'v1'};
 const resultFor=source=>{
  const error=source.includes('raise ValueError')?'ValueError: wrong exercise':source.includes('..')?'SyntaxError: invalid syntax (<student>, line 1)':null;
  return {ok:!error,goalMet:!error,error,pack:{id:'datascience',stdout:error?'':'A: 15 · B: 40 · C: 100',
   execution_status:error?'student_error':'completed',error_line:error?1:null,checks:error?[]:[{ok:true,detail:'Fixed exercise check passed'}]}};
 };
 window.fetch=async(url,options={})=>{
  const path=new URL(url,location.href).pathname, method=options.method||'GET',body=JSON.parse(options.body||'{}');
  window.fixtureRequests.push({path,method});let data,status=200;
  if(path==='/api/curriculum') data={modules:[{exercises:Object.keys(assignments).map((id,i)=>({id,title:['01 · Grouped summaries','02 · Held-out regression','03 · Neural network'][i],prompt:'Fixed browser fixture: use Run code to inspect result and tutor feedback.',starter:'print("A: 15 · B: 40 · C: 100")'}))}]};
  else if(path.endsWith('/jobs/config')) data={recovery_scope:scope,learner_id:identity.learner_id,assignments,poll_seconds:1,result_seconds:300,notice:'Offline fixture'};
  else if(path==='/api/conversations/config') data={controlled:true,recovery_scope:scope,identity,assignments,enabled:true,policy_id:'offline-test-only',retention_seconds:3600};
  else if(path==='/api/run') data=resultFor(body.source);
  else if(path==='/api/conversations') {data={conversation_id:'fixture-'+(++serial),revision:0};conversations.set(data.conversation_id,[]);}
  else if(path.endsWith('/jobs') && method==='POST') {
   const id=(++serial).toString(16).padStart(64,'0'),cid=path.includes('/conversations/')?path.split('/')[3]:null;
   const run=body.result||{},error=run.error;
   const reply=error?`**Local model stub**: ${error.startsWith('SyntaxError')?'SyntaxError means Python cannot parse line 1. Check the punctuation on that line before rerunning.':'ValueError means an operation received an unsuitable value on line 1. Check that this code uses the selected exercise’s files and expected input shape.'}`:'**Local model stub**: Your code executed and the fixed check passed.\n\n- Check the category mean.\n- Inspect `result`.\n\n```python\nprint(result)\n```\n\nWhat does each category’s mean represent?';
   const history=cid?conversations.get(cid):null;
   if(history) history.push({sequence:history.length+1,request_id:body.request_id,role:'student',text:body.message,status:'completed'}, {sequence:history.length+2,request_id:body.request_id,role:'assistant',text:reply,status:'completed'});
   const turn={message:reply,glass_box:{evidence:error?'Your latest code run reported an error.':'Your latest code run completed.',
    approach:'I focused on a possible cause and a small next check.'},...(cid?{conversation_id:cid,revision:history.length}:{})};
   const job={id,state:body.source?.includes('BUDGET_BLOCK')?'failed':'completed',reason:body.source?.includes('BUDGET_BLOCK')?'budget_exhausted':null,result:turn};jobs.set(body.request_id,job);
   data={id,state:'queued'};status=202;
  } else if(path.includes('/by-request/')) {data=jobs.get(decodeURIComponent(path.split('/').at(-1)));if(!data){status=404;data={detail:{code:'job_unavailable'}};}}
  else if(path.endsWith('/messages')) {const messages=conversations.get(path.split('/')[3])||[];data={messages,revision:messages.length,pending:false,before:null};}
  else throw Error('Offline fixture rejected unexpected request');
  await new Promise(r=>setTimeout(r,150));
  return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
 };
 document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('backend').value=base;
  document.title='Belay · Offline feedback browser fixture';
 });
})();
