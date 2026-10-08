import { FALLBACK_ASSETS } from "../deploy/fallback-assets.js";
import { STATUS_ASSETS } from "../deploy/status-assets.js";
import { recordProbe, readHistory } from "../deploy/status-history.js";

/**
 * Reemplaza al Caddy de la VM como origen de los dominios públicos.
 *
 * Configurar como Worker de zona para `*.seismik.org/*` y `seismik.org/*`.
 * No contiene secretos: el de origen llega como secreto del Worker.
 */
const API = "https://seismik-api-331950364408.us-east1.run.app";
const WEB = "https://seismik-web-331950364408.us-east1.run.app";
const FIREBASE = "https://seismik-15bbb.firebaseapp.com";

// La API rechaza lo que llega a su URL directa de Cloud Run sin este secreto,
// para que nadie salte las cabeceras y la protección de Cloudflare. El valor
// vive como secreto del Worker (`EDGE_ORIGIN_SECRET`), nunca en el código.
const ORIGIN_AUTH_HEADER = "X-Seismik-Origin-Auth";

async function isAvailable(url, init = {}) {
  try {
    return (await fetch(url, { ...init, signal: AbortSignal.timeout(5000) })).ok;
  } catch {
    return false;
  }
}

// La página de estado ve únicamente disponibilidad pública. La comprobación
// de la API sale por el mismo secreto de origen que usa el enrutador; ningún
// secreto, métrica interna ni dato de usuarios llega al navegador.
async function publicStatus(env) {
  const apiHeaders = env?.EDGE_ORIGIN_SECRET ? { [ORIGIN_AUTH_HEADER]: env.EDGE_ORIGIN_SECRET } : {};
  const [api, web, developers] = await Promise.all([
    isAvailable(`${API}/health/ready`, { headers: apiHeaders }),
    isAvailable(`${WEB}/`),
    isAvailable(`${WEB}/developers.html`),
  ]);
  return Response.json({
    checked_at: new Date().toISOString(),
    services: { api, web, developers },
  }, { headers: { "Cache-Control": "no-store" } });
}

function targetFor(request) {
  const source = new URL(request.url);
  const host = source.hostname;
  let origin = WEB;
  let path = source.pathname;
  if (host === "api.seismik.org") origin = API;
  else if (host === "ifeltit.seismik.org") {
    if (path.startsWith("/v1/reports/")) origin = API;
    else if (path === "/") path = "/ifeltit.html";
  } else if (host === "devs.seismik.org") {
    if (path.startsWith("/v1/")) origin = API;
    else if (path.startsWith("/__/auth/")) origin = FIREBASE;
    else if (path === "/") path = "/developers.html";
  } else if (host === "admin.seismik.org") {
    if (path.startsWith("/v1/")) origin = API;
    else if (path === "/") path = "/admin/";
  } else if (host === "status.seismik.org") {
    if (path === "/") path = "/status.html";
  } else if (host === "auth.seismik.org") {
    if (path === "/") return new URL("https://devs.seismik.org/");
    else if (path === "/id" || path === "/id/") path = "/auth.html";
    else if (path.startsWith("/v1/oauth/") || path.startsWith("/id/") || path === "/login") origin = API;
  } else if (host === "www.seismik.org") return new URL(`https://seismik.org${path}${source.search}`);
  else if (host === "seismik.org") {
    if (path.startsWith("/v1/")) origin = API;
    else if (path === "/privacy.html") return new URL("https://seismik.org/terms-of-privacy/");
    else if (path === "/api-terms.html") return new URL("https://seismik.org/terms-of-service/#api");
  }
  return new URL(`${path}${source.search}`, origin);
}

function securityHeaders(host, nonce = "") {
  const headers = new Headers({
    // No se guarda la respuesta API ni el acceso OAuth. El portal no contiene
    // secretos en HTML: permitir revalidación privada conserva bfcache al ir
    // atrás/adelante y `pageshow` vuelve a consultar la sesión.
    "Cache-Control": host === "api.seismik.org" || host === "auth.seismik.org" || host === "status.seismik.org" || host === "admin.seismik.org"
      ? "no-store"
      : "private, no-cache",
    "Permissions-Policy": host === "ifeltit.seismik.org"
      ? "camera=(), microphone=(), geolocation=(self)"
      : "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  });
  if (host === "api.seismik.org") headers.set("Content-Security-Policy", "default-src 'none'; base-uri 'none'; frame-ancestors 'none'");
  else if (host === "devs.seismik.org" || host === "auth.seismik.org") headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self' https://www.gstatic.com https://challenges.cloudflare.com; style-src 'self'; img-src 'self' data: https://lh3.googleusercontent.com; connect-src 'self' https://api.seismik.org https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; frame-src 'self' https://accounts.google.com https://seismik-15bbb.firebaseapp.com https://challenges.cloudflare.com; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  else if (host === "ifeltit.seismik.org") {
    headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    headers.set("Content-Security-Policy", `default-src 'self'; script-src 'self' 'nonce-${nonce}' https://challenges.cloudflare.com https://maps.googleapis.com https://maps.gstatic.com; style-src 'self' 'nonce-${nonce}' https://fonts.googleapis.com; img-src 'self' data: https://*.googleapis.com https://*.gstatic.com https://*.google.com https://*.googleusercontent.com; connect-src 'self' https://api.seismik.org https://*.googleapis.com https://*.gstatic.com https://*.google.com; frame-src https://challenges.cloudflare.com https://*.google.com; font-src 'self' https://fonts.gstatic.com; worker-src blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`);
  }
  else if (host === "status.seismik.org") headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
  else if (host === "admin.seismik.org") {
    headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
    headers.set("X-Robots-Tag", "noindex, nofollow");
  }
  else headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self'; img-src 'self' data:; connect-src 'self' https://api.seismik.org; frame-src https://challenges.cloudflare.com; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  return headers;
}

// Se sirve desde el Worker, incluso si el servidor estático está caído.
function fallbackResponse(request, outage = false) {
  const url = new URL(request.url);
  const path = outage ? "/offline.html" : url.pathname;
  const body = FALLBACK_ASSETS[path];
  const headers = securityHeaders(url.hostname);
  headers.set("Content-Type", path.endsWith(".css") ? "text/css; charset=utf-8" : path.endsWith(".js") ? "application/javascript; charset=utf-8" : "text/html; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  if (outage) {
    headers.set("Retry-After", "60");
    headers.set("X-Seismik-Fallback", "1");
  }
  return new Response(request.method === "HEAD" ? null : body, { status: outage ? 503 : 200, headers });
}

function unavailableResponse(request, target) {
  const acceptsHTML = request.headers.get("Accept")?.includes("text/html");
  if (target.origin === WEB && ["GET", "HEAD"].includes(request.method) && acceptsHTML) {
    return fallbackResponse(request, true);
  }
  // Los clientes API y OAuth mantienen respuestas de error, nunca HTML.
  const headers = securityHeaders(new URL(request.url).hostname);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Retry-After", "60");
  return new Response(request.method === "HEAD" ? null : JSON.stringify({ detail: "Service temporarily unavailable" }), { status: 503, headers });
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil((async () => {
      const status = await (await publicStatus(env)).json();
      await recordProbe(env.STATUS_DB, status, controller.scheduledTime);
    })());
  },
  async fetch(request, env) {
    const source = new URL(request.url);
    if (source.hostname === "status.seismik.org" && source.pathname === "/api/history") {
      if (request.method !== "GET") return new Response("Method not allowed", { status: 405 });
      try {
        return Response.json(await readHistory(env?.STATUS_DB), { headers: securityHeaders(source.hostname) });
      } catch {
        return Response.json({ available: false, days: [] }, { status: 503, headers: securityHeaders(source.hostname) });
      }
    }
    if (source.hostname === "status.seismik.org" && source.pathname === "/api/status") {
      if (request.method !== "GET") return new Response("Method not allowed", { status: 405 });
      const response = await publicStatus(env);
      const headers = new Headers(response.headers);
      for (const [name, value] of securityHeaders(source.hostname)) headers.set(name, value);
      return new Response(response.body, { status: response.status, headers });
    }
    // Status assets live at the edge so the history remains visible during web outages.
    if (source.hostname === "status.seismik.org" && Object.hasOwn(STATUS_ASSETS, source.pathname)) {
      if (!["GET", "HEAD"].includes(request.method)) return new Response("Method not allowed", { status: 405 });
      const headers = securityHeaders(source.hostname);
      const type = source.pathname.endsWith(".js") ? "application/javascript" : source.pathname.endsWith(".css") ? "text/css" : "text/html";
      headers.set("Content-Type", `${type}; charset=utf-8`);
      return new Response(request.method === "HEAD" ? null : STATUS_ASSETS[source.pathname], { headers });
    }
    if (["GET", "HEAD"].includes(request.method) && Object.hasOwn(FALLBACK_ASSETS, source.pathname) && source.hostname !== "api.seismik.org" && source.hostname !== "auth.seismik.org") {
      return fallbackResponse(request);
    }
    const target = targetFor(request);
    if (target.hostname.endsWith("seismik.org")) return Response.redirect(target, 301);
    const upstreamRequest = new Request(new Request(target, request), { signal: AbortSignal.timeout(8000) });
    // Un cliente no puede fijar la cabecera por su cuenta, y el secreto sólo
    // viaja hacia la API: ni el sitio estático ni Firebase deben verlo.
    upstreamRequest.headers.delete(ORIGIN_AUTH_HEADER);
    upstreamRequest.headers.delete("X-Seismik-Client-IP");
    upstreamRequest.headers.delete("X-Seismik-Admin-Host");
    if (target.origin === API && source.hostname === "admin.seismik.org") {
      upstreamRequest.headers.set("X-Seismik-Admin-Host", source.hostname);
    }
    if (source.hostname === "ifeltit.seismik.org" && ["/", "/ifeltit.html"].includes(source.pathname)) {
      upstreamRequest.headers.delete("If-None-Match");
      upstreamRequest.headers.delete("If-Modified-Since");
    }
    if (target.origin === API && request.headers.get("CF-Connecting-IP")) {
      upstreamRequest.headers.set("X-Seismik-Client-IP", request.headers.get("CF-Connecting-IP"));
    }
    if (target.origin === API && env?.EDGE_ORIGIN_SECRET) upstreamRequest.headers.set(ORIGIN_AUTH_HEADER, env.EDGE_ORIGIN_SECRET);
    let upstream;
    try {
      upstream = await fetch(upstreamRequest);
    } catch {
      return unavailableResponse(request, target);
    }
    if (upstream.status >= 500 && target.origin === WEB && ["GET", "HEAD"].includes(request.method) && request.headers.get("Accept")?.includes("text/html")) {
      return fallbackResponse(request, true);
    }
    const headers = new Headers(upstream.headers);
    const feltHTML = source.hostname === "ifeltit.seismik.org" && upstream.headers.get("Content-Type")?.includes("text/html");
    const nonce = feltHTML ? crypto.randomUUID().replaceAll("-", "") : "";
    for (const [name, value] of securityHeaders(source.hostname, nonce)) headers.set(name, value);
    headers.delete("Server");
    if (feltHTML) {
      headers.set("Cache-Control", "no-store");
      headers.delete("ETag"); headers.delete("Last-Modified");
    }
    const response = new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers });
    if (feltHTML && request.method !== "HEAD") {
      return new HTMLRewriter().on("script", { element(element) { element.setAttribute("nonce", nonce); } }).transform(response);
    }
    return response;
  },
};
