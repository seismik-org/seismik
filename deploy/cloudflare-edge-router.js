/**
 * Reemplaza al Caddy de la VM como origen de los dominios públicos.
 *
 * Configurar como Worker de zona para `*.seismik.org/*` y `seismik.org/*`.
 * No contiene secretos: sólo decide el origen gestionado según host y ruta.
 */
const API = "https://seismik-api-331950364408.us-east1.run.app";
const WEB = "https://seismik-web-331950364408.us-east1.run.app";
const FIREBASE = "https://seismik-15bbb.firebaseapp.com";

function targetFor(request) {
  const source = new URL(request.url);
  const host = source.hostname;
  let origin = WEB;
  let path = source.pathname;

  if (host === "api.seismik.org") {
    origin = API;
  } else if (host === "devs.seismik.org") {
    if (path.startsWith("/v1/")) origin = API;
    else if (path.startsWith("/__/auth/")) origin = FIREBASE;
    else if (path === "/") path = "/developers.html";
  } else if (host === "auth.seismik.org") {
    if (path.startsWith("/v1/oauth/") || path.startsWith("/id/") || path === "/login") {
      origin = API;
    } else if (path === "/") {
      return new URL("https://devs.seismik.org/");
    } else if (path === "/id" || path === "/id/") {
      path = "/auth.html";
    }
  } else if (host === "www.seismik.org") {
    return new URL(`https://seismik.org${path}${source.search}`);
  } else if (host === "seismik.org") {
    if (path === "/privacy.html") return new URL("https://seismik.org/terms-of-privacy");
    if (path === "/api-terms.html") return new URL("https://seismik.org/terms-of-service#api");
  }
  return new URL(`${path}${source.search}`, origin);
}

export default {
  async fetch(request) {
    const target = targetFor(request);
    if (target.hostname.endsWith("seismik.org")) return Response.redirect(target, 301);
    return fetch(new Request(target, request));
  },
};
