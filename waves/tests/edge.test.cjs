const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

let seen;
const context = {URL, Request, Response, Headers, AbortSignal, fetch: async (url, options) => {
  seen = {url, options};
  return options.method === 'POST' ? new Response(null, {status: 204, headers: {'set-cookie': 'bad=1'}})
    : new Response('{"detail":"x"}', {status: 200, headers: {'set-cookie': 'bad=1', 'content-type': 'application/json'}});
}};
vm.createContext(context);
const source = fs.readFileSync(path.join(__dirname, '../edge/worker.js'), 'utf8').replace('export default', 'globalThis.worker =');
vm.runInContext(source, context);

// Workers Static Assets: sólo existen los archivos de static/, igual que en el despliegue.
const files = {'/index.html': ['<html>portal</html>', 'text/html'], '/explore.html': ['<html>explorador</html>', 'text/html'], '/waves.js': ['// js', 'text/javascript'],
  '/404.html': ['<html>404</html>', 'text/html'],
  '/robots.txt': ['User-agent: *\nAllow: /\n', 'text/plain'],'/sitemap.xml': ['<urlset/>', 'application/xml'], '/llms.txt': ['# Waves', 'text/plain']};
const env = {ASSETS: {fetch: async request => {
  const entry = files[new URL(request.url).pathname];
  return entry ? new Response(entry[0], {status: 200, headers: {'content-type': entry[1], 'set-cookie': 'bad=1'}})
    : new Response('missing', {status: 404});
}}};
const get = (url, init) => context.worker.fetch(new Request(url, init), env);
const cookies = response => response.headers.getSetCookie();

(async () => {
  // --- Backend privado: se reenvía a Cloud Run, sólo con la cookie de sesión de Seismik ------------------------
  const api = await get('https://waves.seismik.org/v1/waves/catalog?q=abc', {headers: {
    Cookie: 'analytics=1; seismik_session=abc.DEF-123_x=; other=2', Authorization: 'Bearer ignorado'}});
  assert.equal(seen.url, 'https://seismik-waves-izkzxyaukq-ue.a.run.app/v1/waves/catalog?q=abc');
  assert.equal(seen.options.headers.get('Cookie'), 'seismik_session=abc.DEF-123_x=', 'sólo viaja la cookie de sesión, intacta');
  assert.equal(seen.options.redirect, 'manual');
  assert.equal(api.headers.get('Cache-Control'), 'private, no-store');
  assert.deepEqual(cookies(api), [], 'el origen nunca puede fijar cookies');
  await get('https://waves.seismik.org/v1/waves/summary', {headers: {Cookie: 'otra=1'}});
  assert.equal(seen.options.headers.get('Cookie'), null, 'sin sesión no viaja ninguna cookie');
  seen = undefined;
  await get('https://waves.seismik.org/health/ready');
  assert.equal(seen.url, 'https://seismik-waves-izkzxyaukq-ue.a.run.app/health/ready');

  // --- Acceso: igual que admin.seismik.org, por auth.seismik.org ------------------------------------------------
  const login = await get('https://waves.seismik.org/login');
  assert.equal(login.status, 303);
  assert.equal(login.headers.get('Location'), 'https://auth.seismik.org/id');
  assert.deepEqual(cookies(login), ['seismik_after_login=waves; Domain=.seismik.org; Path=/; Max-Age=600; Secure; HttpOnly; SameSite=None']);
  assert.equal(login.headers.get('Cache-Control'), 'private, no-store');
  const loginQuery = await get('https://waves.seismik.org/login?next=https://evil.example');
  assert.equal(loginQuery.headers.get('Location'), 'https://auth.seismik.org/id', 'el destino no se puede elegir');

  // --- Cierre de sesión: sólo POST desde el propio portal; el Worker borra la cookie compartida ------------------
  seen = undefined;
  const logout = await get('https://waves.seismik.org/v1/waves/logout', {method: 'POST', headers: {Origin: 'https://waves.seismik.org', Cookie: 'seismik_session=abcdefghijklmnopqrstuvwxyz'}});
  assert.equal(logout.status, 204);
  assert.equal(seen.options.method, 'POST');
  assert.equal(seen.options.headers.get('Cookie'), 'seismik_session=abcdefghijklmnopqrstuvwxyz');
  assert.deepEqual(cookies(logout), ['seismik_session=; Domain=.seismik.org; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax']);
  seen = undefined;
  for (const origin of [undefined, 'https://evil.example', 'https://waves.seismik.org.evil.example', 'http://waves.seismik.org']) {
    const rejected = await get('https://waves.seismik.org/v1/waves/logout', {method: 'POST', headers: origin ? {Origin: origin} : {}});
    assert.equal(rejected.status, 403, String(origin));
    assert.deepEqual(cookies(rejected), []);
  }
  assert.equal(seen, undefined, 'un cierre de sesión ajeno no llega al backend');
  assert.equal((await get('https://waves.seismik.org/v1/waves/catalog', {method: 'POST', headers: {Origin: 'https://waves.seismik.org'}})).status, 405);

  // --- Portal estático: sale del Worker y nunca toca el backend --------------------------------------------------
  seen = undefined;
  const home = await get('https://waves.seismik.org/');
  assert.equal(home.status, 200);
  assert.equal(await home.text(), '<html>portal</html>');
  assert.equal(seen, undefined, 'la portada no consulta ningún origen externo');
  const viewer = await get('https://waves.seismik.org/explore?id=abc');
  assert.equal(await viewer.text(), '<html>explorador</html>');
  assert.equal((await get('https://waves.seismik.org/explore.html')).status, 404);
  const old = await get('https://waves.seismik.org/explorar?id=abc');
  assert.equal(old.status, 308);
  assert.equal(old.headers.get('Location'), 'https://waves.seismik.org/explore?id=abc', 'el nombre anterior redirige y conserva la consulta');
  const script = await get('https://waves.seismik.org/assets/waves.js');
  assert.equal(script.status, 200);
  assert.equal(script.headers.get('content-type'), 'text/javascript');
  assert.deepEqual(cookies(script), []);

  // --- Para buscadores y modelos de IA: públicos y guardables una hora ---------------------------------------------
  for (const [route, body] of [['/robots.txt', 'User-agent: *\nAllow: /\n'],['/sitemap.xml', '<urlset/>'], ['/llms.txt', '# Waves']]) {
    const found = await get('https://waves.seismik.org' + route);
    assert.equal(found.status, 200, route);
    assert.equal(await found.text(), body, route);
    assert.equal(found.headers.get('Cache-Control'), 'public, max-age=3600', route);
    assert.equal(found.headers.get('set-cookie'), null);
  }
  assert.equal((await get('https://waves.seismik.org/robots.txt', {headers: {'User-Agent': 'GPTBot/1.1'}})).status, 200, 'los rastreadores de IA no reciben un trato distinto');

  // --- Cabeceras de seguridad en todas las respuestas --------------------------------------------------------------
  const csp = home.headers.get('Content-Security-Policy');
  assert.match(csp, /script-src 'self';/);
  assert.match(csp, /connect-src 'self';/);
  assert.match(csp, /frame-src 'none';/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.doesNotMatch(csp, /unsafe-|google|gstatic|firebase/);
  assert.equal(api.headers.get('Content-Security-Policy'), csp);
  assert.equal(home.headers.get('Cache-Control'), 'private, no-store');
  assert.equal(home.headers.get('X-Frame-Options'), 'DENY');
  assert.ok(home.headers.get('Strict-Transport-Security'));

  // --- Lo que no es del portal ni del backend ------------------------------------------------------------------------
  for (const route of ['/catalog.json', '/firebase-public.json', '/app.py', '/index.html', '/assets/../app.py', '/assets/../../x', '/assets/nada.js', '/otra-ruta']) {
    const miss = await get('https://waves.seismik.org' + route);
    assert.equal(miss.status, 404, route);
    assert.equal(await miss.text(), '<html>404</html>', route);
  }
  assert.equal((await get('https://evil.example/')).status, 404);
  assert.equal((await get('https://waves.seismik.org/', {method: 'POST'})).status, 405);
  const redirect = await get('http://waves.seismik.org/test');
  assert.equal(redirect.status, 308);
  assert.equal(redirect.headers.get('Location'), 'https://waves.seismik.org/test');

  // --- Si el backend cae, el portal sigue cargando y la API responde 503 -----------------------------------------------
  context.fetch = async () => { throw new Error('caído'); };
  const down = await get('https://waves.seismik.org/v1/waves/summary');
  assert.equal(down.status, 503);
  assert.equal((await get('https://waves.seismik.org/')).status, 200);
  console.log('Edge tests passed: static portal, login hand-off to auth.seismik.org, session cookie only, logout, headers, 404s and method limits.');
})().catch(error => { console.error(error); process.exitCode = 1; });
