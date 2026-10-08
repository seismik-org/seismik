// Sólo guarda el respaldo público; nunca respuestas API, OAuth o datos personales.
const CACHE_PREFIX = "seismik-fallback-";
const CACHE = CACHE_PREFIX + "b73c54590c1b279b";
const ASSETS = ["/offline.html", "/offline.css", "/footer.css", "/offline.js", "/site.js"];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then(async (cache) => {
    for (const path of ASSETS) {
      const response = await fetch(path, { cache: "reload" });
      if (!response.ok || response.headers.get("X-Seismik-Fallback")) throw new Error("Respaldo incompleto");
      await cache.put(path, response);
    }
    await self.skipWaiting();
  }));
});
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith(CACHE_PREFIX) && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    // Deja API y autenticación fuera del respaldo HTML.
    if (/^\/(?:v1(?:\/|$)|api(?:\/|$)|__\/auth(?:\/|$)|id(?:\/|$)|login(?:\/|$))/.test(url.pathname)) return;
    event.respondWith((async () => {
      let connection = "unavailable";
      try {
        const response = await fetch(request, { signal: AbortSignal.timeout(8000) });
        if (response.status < 500) return response;
      } catch { connection = "offline"; }
      const fallback = await caches.match("/offline.html", { cacheName: CACHE });
      if (!fallback) return Response.error();
      const html = (await fallback.text()).replace("<body>", `<body data-connection="${connection}">`);
      const headers = new Headers(fallback.headers);
      headers.delete("Content-Length");
      headers.set("Cache-Control", "no-store");
      return new Response(html, { status: 503, headers });
    })());
  } else if (ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(url.pathname, { cacheName: CACHE }).then((cached) => cached || fetch(request)));
  }
});
