import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function fixture() {
  const nodes = new Map();
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'',textContent:'',hidden:false,open:false,handlers:{},
      addEventListener(event,fn) {this.handlers[event]=fn;},
      showModal(){this.open=true;}, close(){this.open=false;},focus(){}});
    return nodes.get(id);
  };
  const calls=[];
  const context = {$, URLSearchParams, location:{search:'?admin_code=one-use-ticket',pathname:'/'},
    history:{replaceState(...args){calls.push(['history',args]);}},showUser(){},start:async()=>{},
    api:async(path,options)=>{calls.push([path,options]);
      if(path.endsWith('/status')) return {enrolled:false,verified:false,email:'admin@example.com'};
      if(path.endsWith('/verify')) return {approval:'action-token',recovery_codes:[]};
      return {ok:true};},
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/admin-mfa.js','utf8'),context);
  return {$,context,calls};
}

test('handoff is removed from the URL before exchange; pre-MFA cannot show the panel',async()=>{
  const {$,context,calls}=fixture();
  assert.equal(await vm.runInContext('adminAuthenticate()',context),false);
  assert.equal(calls[0][0],'history');
  assert.equal(calls[1][0],'/v1/admin/auth/exchange');
  assert.equal($('#app').hidden,true);
  assert.equal($('#mfa').hidden,false);
});

test('action dialog submits the exact action and clears the code after verification',async()=>{
  const {$,context,calls}=fixture();
  const result=vm.runInContext('approveAction("control:alerts:false","Pausar alertas")',context);
  $('#action-code').value='123456';
  await $('#action-form').handlers.submit({preventDefault(){}});
  assert.equal(await result,'action-token');
  assert.deepEqual(JSON.parse(calls[0][1].body),{code:'123456',action:'control:alerts:false'});
  assert.equal($('#action-code').value,'');
  assert.equal($('#action-mfa').open,false);
});

test('cancelling an action cannot submit a change; clearing data erases MFA secrets',async()=>{
  const {$,context,calls}=fixture();
  const result=vm.runInContext('approveAction("control:x:false","Pausar X")',context);
  $('#mfa-secret').textContent='secret'; $('#mfa-recovery').textContent='backup';
  vm.runInContext('clearMfa()',context);
  assert.equal(await result,null);
  assert.equal(calls.length,0);
  assert.equal($('#mfa-secret').textContent,'');
  assert.equal($('#mfa-recovery').textContent,'');
});
