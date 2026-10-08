import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function fixture() {
  const nodes = new Map();
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'',textContent:'',hidden:false,open:false,handlers:{},
      addEventListener(event,fn) {this.handlers[event]=fn;},
      showModal(){this.open=true;}, close(){this.open=false;},focus(){},getContext(){return {fillRect(){}}}});
    return nodes.get(id);
  };
  const calls=[];
  const timers=[];
  const context = {$, URLSearchParams, setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){},window:{addEventListener(){}}, location:{search:'?admin_code=one-use-ticket',pathname:'/'},
    history:{replaceState(...args){calls.push(['history',args]);}},showUser(){},start:async()=>{},
    api:async(path,options)=>{calls.push([path,options]);
      if(path.endsWith('/status')) return {enrolled:false,verified:false,email:'admin@example.com'};
      if(path.endsWith('/enroll')) return {secret:'JBSWY3DPEHPK3PXP',uri:'otpauth://totp/Seismik%20Admin:admin%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=Seismik%20Admin'};
      if(path.endsWith('/verify')) return {approval:'action-token',recovery_codes:[]};
      return {ok:true};},
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/vendor/qrcodegen.js','utf8'),context);
  vm.runInContext(readFileSync('web/admin-mfa.js','utf8'),context);
  return {$,context,calls,timers};
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


test('enrollment renders a local QR, retains manual fallback and erases it on expiry',async()=>{
  const {$,calls,timers}=fixture();
  await $('#mfa-enroll').handlers.click();
  assert.equal($('#mfa-secret').textContent,'JBSWY3DPEHPK3PXP');
  assert.ok($('#mfa-qr').width>200);
  assert.equal($('#mfa-qr').width,$('#mfa-qr').height);
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],'/v1/admin/auth/enroll');
  timers[0]();
  assert.equal($('#mfa-secret').textContent,'');
  assert.equal($('#mfa-qr').width,0);
  assert.equal($('#mfa-form').hidden,true);
});

test('late enrollment response after logout cannot restore a QR or a secret',async()=>{
  const {$,context}=fixture();
  let resolve;
  context.api=()=>new Promise(r=>{resolve=r;});
  const request=$('#mfa-enroll').handlers.click();
  vm.runInContext('clearMfa()',context);
  resolve({secret:'late-secret',uri:'otpauth://late'});
  await request;
  assert.equal($('#mfa-secret').textContent,'');
  assert.equal($('#mfa-qr').width,0);
});
