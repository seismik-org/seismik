// Wrap the existing Worker without changing its bindings or private routes.
import original from './__ORIGINAL_MAIN__';

const BRAND = '__BRAND__';
const PRIMARY = '__PRIMARY__';
const ALTERNATE = '__ALTERNATE__';
const PRIMARY_HOSTS = __PRIMARY_HOSTS__;
const VERSION = '20261101';
const PREFIX = '/__continuity/';
const publicPath = path => ['/', '/grupo/', '/preguntas-frecuentes/', '/modo-emergencia/', '/politicas/', '/privacidad.html', '/terminos.html', '/liveahora/', '/liveahora/politicas/'].includes(path);
const mirrorPath = path => publicPath(path) || /^\/(?:assets\/|liveahora\/[^/]+\.(?:css|js)$|_next\/static\/|[^/]+\.(?:css|js|png|ico|svg|webp|woff2?)$)/.test(path);
const htmlEscape = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');

function offlinePage() {
  return `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${BRAND} · Acceso de respaldo</title><style>body{font:17px/1.7 system-ui;background:#f5f7fb;color:#112039;margin:0;padding:24px}main{max-width:720px;margin:8vh auto;background:white;padding:clamp(24px,6vw,56px);border:1px solid #dde3ee;border-radius:24px}a{color:#075fb7;overflow-wrap:anywhere}h1{line-height:1.15}small{color:#53627c}@media(prefers-color-scheme:dark){body{background:#09101d;color:#edf4ff}main{background:#131e30;border-color:#30405b}a{color:#8ac4ff}}</style><main><small>ACCESO DE RESPALDO</small><h1>${BRAND}</h1><p>Esta es una copia informativa para problemas de conexión o resolución del dominio. No muestra información privada ni confirma operaciones.</p><p><a href="https://${ALTERNATE}/">Abrir acceso alternativo</a><br><a href="https://${PRIMARY}/">Volver al sitio principal</a></p><p>Guarda la dirección alternativa antes de necesitarla. Si también está bloqueada, no hay conexión o Cloudflare falla, este acceso tampoco podrá actualizarse.</p><p>Los datos de cuentas, solicitudes, pagos, eventos nuevos y otras funciones en línea requieren conexión y su servicio habitual.</p><small>Versión de respaldo ${VERSION}. Este sitio no modifica el DNS del dispositivo ni evita todos los tipos de bloqueo.</small></main></html>`;
}

const registration = `if('serviceWorker' in navigator){addEventListener('load',()=>navigator.serviceWorker.register('/sw.js',{scope:'/'}).catch(()=>{}));}`;
const sw = `const C='public-continuity-${VERSION}',P='${PREFIX}offline';
self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(async c=>{const r=await fetch(P,{cache:'reload'});if(!r.ok)throw Error('fallback');await c.put(P,r);await self.skipWaiting()})));
self.addEventListener('activate',e=>e.waitUntil((async()=>{for(const k of await caches.keys())if(k.startsWith('public-continuity-')&&k!==C)await caches.delete(k);await self.clients.claim()})()));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==location.origin||e.request.mode!=='navigate'||!(${publicPath.toString()})(u.pathname))return;e.respondWith((async()=>{try{const r=await fetch(e.request,{signal:AbortSignal.timeout(7000)});if(r.status<500)return r}catch{}return await caches.match(P,{cacheName:C})||Response.error()})())});`;

function asset(request) {
  const pathname = new URL(request.url).pathname;
  const path = pathname === '/sw.js' ? PREFIX+'sw.js' : pathname;
  if (!['GET','HEAD'].includes(request.method)) return new Response('Method not allowed',{status:405});
  const headers = new Headers({'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','X-Robots-Tag':'noindex, nofollow','Service-Worker-Allowed':'/'});
  let data;
  if(path===PREFIX+'sw.js'){data=sw;headers.set('Content-Type','application/javascript; charset=utf-8');}
  else if(path===PREFIX+'register.js'){data=registration;headers.set('Content-Type','application/javascript; charset=utf-8');}
  else if(path===PREFIX+'style.css'){data='.continuity-link{display:block;text-align:center;font:13px/1.5 system-ui;padding:12px 20px;color:inherit;background:transparent}.continuity-banner{padding:14px 24px;background:#fff2cb;color:#342100;font:15px/1.6 system-ui}.continuity-banner a{color:#17467c}';headers.set('Content-Type','text/css; charset=utf-8');}
  else if(path===PREFIX+'offline'){data=offlinePage();headers.set('Content-Type','text/html; charset=utf-8');headers.set('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");}
  else return new Response('Not found',{status:404});
  return new Response(request.method==='HEAD'?null:data,{headers});
}

export default {
  ...original,
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const alternate = url.hostname === ALTERNATE;
    const publicHost = PRIMARY_HOSTS.includes(url.hostname);
    if ((alternate || publicHost) && (url.pathname.startsWith(PREFIX) || url.pathname==='/sw.js')) return asset(request);
    if (alternate && (!['GET','HEAD'].includes(request.method) || !mirrorPath(url.pathname))) {
      return new Response('Acceso alternativo informativo. Las operaciones privadas requieren el sitio principal.',{status:403,headers:{'Cache-Control':'no-store','X-Robots-Tag':'noindex'}});
    }
    let incoming = request;
    if (alternate) {
      const target = new URL(request.url); target.hostname=PRIMARY;
      const headers = new Headers(request.headers);
      headers.set('Host',PRIMARY);
      for (const name of ['Cookie','Authorization','X-Seismik-API-Key','X-Seismik-Account-Session','X-Seismik-Device-Session']) headers.delete(name);
      incoming = new Request(target,{method:request.method,headers,redirect:'manual'});
    }
    const response = await original.fetch(incoming,env,ctx);
    if (!response.headers.get('Content-Type')?.includes('text/html') || !['GET','HEAD'].includes(request.method) || (!alternate && (!publicHost || !publicPath(url.pathname)))) return response;
    const headers = new Headers(response.headers);
    headers.delete('Content-Length');headers.delete('ETag');
    const copy = new Response(response.body,{status:response.status,statusText:response.statusText,headers});
    if (alternate) {
      copy.headers.delete('Set-Cookie');
      copy.headers.set('Cache-Control','no-store');copy.headers.set('X-Robots-Tag','noindex, nofollow');
      copy.headers.set('Content-Security-Policy',"default-src 'self'; script-src 'none'; connect-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
      return new HTMLRewriter().on('body',{element(e){e.prepend(`<aside class="continuity-banner">Acceso alternativo informativo · sin actualizaciones en vivo, cuentas ni operaciones. <a href="https://${PRIMARY}/">Sitio principal</a></aside>`,{html:true})}}).on('script',{element(e){e.remove()}}).on('noscript',{element(e){e.remove()}}).on('form',{element(e){e.remove()}}).on('#schedule-status',{element(e){e.setInnerContent('Acceso de respaldo: visita los canales oficiales para consultar las transmisiones. El cronograma no se actualiza aquí.')}}).on('head',{element(e){e.append(`<link rel="stylesheet" href="${PREFIX}style.css">`,{html:true})}}).transform(copy);
    }
    if (request.method==='HEAD') return copy;
    const alternatePath = url.hostname === 'liveahora.seismik.org' ? '/liveahora/' : '/';
    const label = url.hostname === 'liveahora.seismik.org' ? 'LiveAhora' : BRAND;
    return new HTMLRewriter().on('head',{element(e){e.append(`<link rel="stylesheet" href="${PREFIX}style.css"><script defer src="${PREFIX}register.js"></script>`,{html:true})}}).on('body',{element(e){e.append(`<a class="continuity-link" href="https://${ALTERNATE}${alternatePath}" rel="nofollow">¿No abre el dominio? Guarda el acceso alternativo de ${htmlEscape(label)} ↗</a>`,{html:true})}}).transform(copy);
  }
};
