import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function panel() {
  class Node {
    constructor() { this.value=''; this.textContent=''; this.children=[]; }
    replaceChildren(...items) { this.children=items; }
    append(...items) { this.children.push(...items); }
    addEventListener() {}
    setAttribute() {}
    querySelectorAll() { return []; }
  }
  const nodes=new Map();
  const $=id => { if (!nodes.has(id)) nodes.set(id,new Node()); return nodes.get(id); };
  $('#record-stream').value='official'; $('#record-limit').value='100';
  const requests=[];
  const context={ $, document:{querySelectorAll:()=>[]}, window:{addEventListener(){},confirm:()=>false},
    element:(tag,cls,text)=>Object.assign(new Node(),{textContent:text}),
    crypto:globalThis.crypto, TextEncoder,
    dateTime:v=>v, ago:v=>v, reports:[], loadReports:async()=>true, adminAuthenticate:async()=>true,
    api:(url)=>url==='/v1/admin/me'
      ? Promise.reject(Object.assign(new Error('Login required'),{status:401}))
      : new Promise((resolve,reject)=>requests.push({url,resolve,reject})),
  };
  vm.createContext(context);
  vm.runInContext(readFileSync('web/admin.js','utf8'),context);
  return {context,$,requests};
}

test('switching registers ignores a late response and clears old entries',async()=>{
  const {context,$,requests}=panel();
  await new Promise(setImmediate);
  const first=vm.runInContext('loadRecords()',context);
  $('#record-stream').value='alerts';
  const second=vm.runInContext('loadRecords()',context);
  requests[1].resolve({records:[],total:3,title:'Alertas'});
  await second;
  requests[0].resolve({records:[],total:9,title:'Sismos'});
  await first;
  assert.match($('#record-count').textContent,/Alertas/);
  assert.doesNotMatch($('#record-count').textContent,/Sismos/);
});

test('a failed register can be retried by opening its tab again',async()=>{
  const {context,$,requests}=panel();
  await new Promise(setImmediate);
  const first=vm.runInContext('openTab("records")',context);
  requests[0].reject(new Error('Offline'));
  await first;
  assert.match($('#record-count').textContent,/Offline/);
  const retry=vm.runInContext('openTab("records")',context);
  assert.equal(requests.length,2);
  requests[1].resolve({records:[],total:0,title:'Sismos'});
  await retry;
  assert.match($('#record-count').textContent,/0 de 0/);
});

test('an expired session clears data and offers sign-in',async()=>{
  const {context,$,requests}=panel();
  await new Promise(setImmediate);
  const request=vm.runInContext('loadRecords()',context);
  requests[0].reject(Object.assign(new Error('Vuelve a iniciar sesión'),{status:401}));
  await request;
  assert.equal($('#app').hidden,true);
  assert.equal($('#gate').hidden,false);
  assert.equal($('#record-list').children.length,0);
});

test('the drill approval fingerprint matches the one the API computes',async()=>{
  const {context}=panel();
  await new Promise(setImmediate);
  // Mismo simulacro y mismo resultado que tests/test_admin_privacy_and_drills.py: si cambia un formato, cambia aquí y en la API.
  const action=await vm.runInContext(`drillAction({critical:true,latitude:5.0721,longitude:-75.5138,magnitude:6.8,depth_km:12.5,
    place:'Simulacro — Eje Cafetero',origin_minutes_ago:2,country_code:'CO',refs:['d5659ff255ec655c']})`,context);
  assert.equal(action,'drill:979dad1ae1e74393');
});

test('clearing data without a running drill poll does not need timers',async()=>{
  const {context}=panel();
  await new Promise(setImmediate);
  assert.doesNotThrow(()=>vm.runInContext('clearData()',context));
});
