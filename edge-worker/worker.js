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

function targetFor(request) {
  const source = new URL(request.url);
  const host = source.hostname;
  let origin = WEB;
  let path = source.pathname;
  if (host === "api.seismik.org") origin = API;
  else if (host === "devs.seismik.org") {
    if (path.startsWith("/v1/")) origin = API;
    else if (path.startsWith("/__/auth/")) origin = FIREBASE;
    else if (path === "/") path = "/developers.html";
  } else if (host === "auth.seismik.org") {
    if (path === "/") return new URL("https://devs.seismik.org/");
    else if (path === "/id" || path === "/id/") path = "/auth.html";
    else if (path.startsWith("/v1/oauth/") || path.startsWith("/id/") || path === "/login") origin = API;
  } else if (host === "www.seismik.org") return new URL(`https://seismik.org${path}${source.search}`);
  else if (host === "seismik.org") {
    if (path === "/privacy.html") return new URL("https://seismik.org/terms-of-privacy");
    if (path === "/api-terms.html") return new URL("https://seismik.org/terms-of-service#api");
  }
  return new URL(`${path}${source.search}`, origin);
}

function securityHeaders(host) {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  });
  if (host === "api.seismik.org") headers.set("Content-Security-Policy", "default-src 'none'; base-uri 'none'; frame-ancestors 'none'");
  else if (host === "devs.seismik.org") headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self' https://www.gstatic.com; style-src 'self'; img-src 'self' data: https://lh3.googleusercontent.com; connect-src 'self' https://api.seismik.org https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; frame-src 'self' https://accounts.google.com https://seismik-15bbb.firebaseapp.com; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  else headers.set("Content-Security-Policy", "default-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  return headers;
}

export default {
  async fetch(request, env) {
    const source = new URL(request.url);
    const target = targetFor(request);
    if (target.hostname.endsWith("seismik.org")) return Response.redirect(target, 301);
    const upstreamRequest = new Request(target, request);
    // Un cliente no puede fijar la cabecera por su cuenta, y el secreto sólo
    // viaja hacia la API: ni el sitio estático ni Firebase deben verlo.
    upstreamRequest.headers.delete(ORIGIN_AUTH_HEADER);
    if (target.origin === API && env?.EDGE_ORIGIN_SECRET) upstreamRequest.headers.set(ORIGIN_AUTH_HEADER, env.EDGE_ORIGIN_SECRET);
    const upstream = await fetch(upstreamRequest);
    const headers = new Headers(upstream.headers);
    for (const [name, value] of securityHeaders(source.hostname)) headers.set(name, value);
    headers.delete("Server");
    return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers });
  },
};
