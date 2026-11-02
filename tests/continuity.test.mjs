import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source=await readFile(new URL('../deploy/continuity-wrapper.mjs',import.meta.url),'utf8');
const forwarded=[];
globalThis.testForwarded=forwarded;
globalThis.HTMLRewriter=class {on(){return this}transform(r){return r}};
const code=source.replace("import original from './__ORIGINAL_MAIN__';",`const original={async fetch(r){globalThis.testForwarded.push(r);return new Response('<html><head></head><body>Public</body></html>',{headers:{'Content-Type':'text/html','Set-Cookie':'private=1'}})}};`)
  .replaceAll('__BRAND__','Seismik').replaceAll('__PRIMARY__','seismik.org').replaceAll('__ALTERNATE__','seismik.todozhop.workers.dev').replace('__PRIMARY_HOSTS__','["seismik.org","liveahora.seismik.org"]');
const worker=(await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))).default;
const get=(url,init)=>worker.fetch(new Request(url,init),{},{});

test('alternate is public read-only and never a private API/login proxy',async()=>{
  for(const path of ['/v1/family/messages','/api/account','/admin/','/login','/setup','/dashboard','//evil.test/','/api%2Fprivate.css','/%252fadmin.css']){
    const r=await get('https://seismik.todozhop.workers.dev'+path);assert.equal(r.status,403,path);
  }
  assert.equal((await get('https://seismik.todozhop.workers.dev/',{method:'POST',body:'private'})).status,403);
});
test('alternate strips credentials and cookies, leaves primary authentication untouched',async()=>{
  const r=await get('https://seismik.todozhop.workers.dev/',{headers:{Cookie:'session=private',Authorization:'Bearer private','X-Seismik-Account-Session':'private'}});
  const upstream=forwarded.at(-1);
  assert.equal(new URL(upstream.url).hostname,'seismik.org');
  for(const h of ['cookie','authorization','x-seismik-account-session'])assert.equal(upstream.headers.get(h),null);
  assert.equal(r.headers.get('set-cookie'),null);
  assert.equal(r.headers.get('x-robots-tag'),'noindex, nofollow');
  assert.match(r.headers.get('content-security-policy'),/connect-src 'none'/);
  await get('https://seismik.org/v1/private',{headers:{Cookie:'session=kept'}});
  assert.equal(forwarded.at(-1).headers.get('cookie'),'session=kept');
});
test('public offline service worker is valid and does not intercept private navigation',async()=>{
  const response=await get('https://seismik.org/sw.js');
  assert.equal(response.headers.get('service-worker-allowed'),'/');
  const js=await response.text();
  const script=new vm.Script(js);
  const handlers={};
  const cached=new Response('Public offline information',{status:503});
  const context=vm.createContext({self:{addEventListener:(n,f)=>handlers[n]=f},URL,AbortSignal,location:{origin:'https://seismik.org'},fetch:async()=>{throw Error('DNS unavailable')},caches:{match:async()=>cached},Response});
  script.runInContext(context);
  let result;
  handlers.fetch({request:{url:'https://seismik.org/',method:'GET',mode:'navigate'},respondWith:p=>result=p});
  assert.equal(await (await result).text(),'Public offline information');
  for(const path of ['/v1/family/messages','/auth','/admin/','/explore','/account','/login']){
    let handled=false;
    handlers.fetch({request:{url:'https://seismik.org'+path,method:'GET',mode:'navigate'},respondWith:()=>handled=true});
    assert.equal(handled,false,path);
  }
});
test('fallback and registration need no third-party assets',async()=>{
  assert.equal((await get('https://seismik.org/__continuity/offline')).status,200);
  const html=await (await get('https://seismik.org/__continuity/offline')).text();
  assert.match(html,/seismik.todozhop.workers.dev/);
  assert.doesNotMatch(html,/<script|<form|<iframe/);
  assert.equal((await get('https://seismik.org/__continuity/sw.js',{method:'POST'})).status,405);
});
