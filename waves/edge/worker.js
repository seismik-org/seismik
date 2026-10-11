// Waves en Cloudflare: este Worker aloja el portal (HTML, CSS y JS salen de Workers Static Assets) y deja la
// autorización y el catálogo privado en el backend `seismik-waves` de Cloud Run. Nada de lo privado viaja en el
// paquete del Worker: el catálogo sólo existe en Cloud Run y allí se comprueba la sesión de Seismik en el servidor.
//
// Acceso, igual que admin.seismik.org: «Entrar» lleva a auth.seismik.org/id, la persona inicia sesión allí y
// Seismik la devuelve a este portal con la cookie `seismik_session` (HttpOnly, de todo *.seismik.org). El Worker
// sólo reenvía esa cookie al backend; ni la lee ni la guarda. No hay SDK de Firebase ni formulario en esta página.
const HOST = "waves.seismik.org";
const BACKEND = "https://seismik-waves-izkzxyaukq-ue.a.run.app";
const AUTH_URL = "https://auth.seismik.org/id";
const SESSION_COOKIE = "seismik_session";
// Marca fija que le dice a auth.seismik.org «al terminar, devuélveme a Waves». No lleva destino: el destino es una
// constante en la API de Seismik, así que no puede usarse como redirección abierta.
const RETURN_MARKER = "seismik_after_login=waves; Domain=.seismik.org; Path=/; Max-Age=600; Secure; HttpOnly; SameSite=None";
const SESSION_CLEAR = `${SESSION_COOKIE}=; Domain=.seismik.org; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax`;
const API_PREFIXES = ["/v1/", "/health/"];
const LOGOUT_PATH = "/v1/waves/logout";

// Si cambias esta política, cambia también waves/app.py: una prueba comprueba que sean idénticas. No añadas
// `Cross-Origin-Opener-Policy`: no hace falta y complica la vuelta desde auth.seismik.org.
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; " +
  "frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";

function hardened(response, status, cookies = []) {
  const result = new Response(response.body, {status: status ?? response.status, headers: response.headers});
  result.headers.set("Cache-Control", "private, no-store");
  result.headers.set("Strict-Transport-Security", "max-age=31536000");
  result.headers.set("X-Content-Type-Options", "nosniff");
  result.headers.set("Referrer-Policy", "no-referrer");
  result.headers.set("Permissions-Policy", "geolocation=(), microphone=(), camera=()");
  result.headers.set("X-Frame-Options", "DENY");
  result.headers.set("Content-Security-Policy", CSP);
  // Ninguna respuesta del origen puede fijar cookies; sólo las dos de este Worker, definidas arriba.
  result.headers.delete("set-cookie");
  for (const cookie of cookies) result.headers.append("set-cookie", cookie);
  return result;
}

function unavailable() {
  return hardened(new Response("Waves no está disponible temporalmente. Vuelve a intentarlo.", {
    status: 503, headers: {"Content-Type": "text/plain; charset=utf-8"}
  }));
}

// De todas las cookies del navegador, el backend sólo recibe la sesión de Seismik.
function sessionCookie(request) {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === SESSION_COOKIE && value.length) return `${SESSION_COOKIE}=${value.join("=")}`;
  }
  return null;
}

async function backend(request, source) {
  const target = new URL(source.pathname + source.search, BACKEND);
  const headers = new Headers(request.headers);
  headers.delete("cookie");
  headers.delete("host");
  headers.delete("x-seismik-origin-auth");
  const session = sessionCookie(request);
  if (session) headers.set("cookie", session);
  try {
    const upstream = await fetch(target.toString(), {
      method: request.method, headers, redirect: "manual",
      signal: AbortSignal.timeout(20000), cf: {cacheTtl: 0, cacheEverything: false}
    });
    const loggedOut = request.method === "POST" && source.pathname === LOGOUT_PATH && upstream.ok;
    return hardened(new Response(upstream.body, upstream), undefined, loggedOut ? [SESSION_CLEAR] : []);
  } catch {
    return unavailable();
  }
}

function login() {
  return hardened(new Response(null, {status: 303, headers: {Location: AUTH_URL}}), undefined, [RETURN_MARKER]);
}

// El portal publica `static/` bajo `/assets/…`, la portada en `/` y el explorador de ondas en `/explore`.
function assetPath(pathname) {
  if (pathname === "/") return "/index.html";
  if (pathname === "/explore") return "/explore.html";
  if (["/robots.txt", "/sitemap.xml", "/llms.txt"].includes(pathname)) return pathname;  // para buscadores y modelos de IA
  if (pathname.startsWith("/assets/")) return pathname.slice("/assets".length);
  return null;
}

async function portal(request, env, source) {
  const file = assetPath(source.pathname);
  if (file && !file.split("/").includes("..") && !file.startsWith("//")) {
    const found = await env.ASSETS.fetch(new Request(new URL(file, source), {method: request.method}));
    if (found.status === 200) {
      const result = hardened(found);
      if (["/robots.txt", "/sitemap.xml", "/llms.txt"].includes(file)) {
        result.headers.set("Cache-Control", "public, max-age=3600");
        result.headers.set("Content-Type", file.endsWith(".xml") ? "application/xml; charset=utf-8" : "text/plain; charset=utf-8");
      }
      return result;
    }
  }
  const missing = await env.ASSETS.fetch(new Request(new URL("/404.html", source)));
  return hardened(missing, 404);
}

export default {
  async fetch(request, env) {
    const source = new URL(request.url);
    if (source.hostname !== HOST) return new Response("Not found", {status: 404});
    if (source.protocol !== "https:") {
      source.protocol = "https:";
      return Response.redirect(source.toString(), 308);
    }
    const isLogout = request.method === "POST" && source.pathname === LOGOUT_PATH;
    if (isLogout && request.headers.get("origin") !== `https://${HOST}`) {
      return hardened(new Response("Forbidden", {status: 403}));
    }
    if (!isLogout && !["GET", "HEAD"].includes(request.method)) {
      return new Response("Method not allowed", {status: 405, headers: {Allow: "GET, HEAD"}});
    }
    if (source.pathname === "/login") return login();
    if (source.pathname === "/explorar") {  // nombre anterior del explorador: los enlaces guardados siguen funcionando
      source.pathname = "/explore";
      return hardened(new Response(null, {status: 308, headers: {Location: source.toString()}}));
    }
    if (API_PREFIXES.some(prefix => source.pathname.startsWith(prefix))) return backend(request, source);
    return portal(request, env, source);
  }
};
