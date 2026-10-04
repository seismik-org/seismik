# Respaldo sin conexión y durante caídas

`web/offline.html` usa el estilo de Seismik con fuentes del sistema y recursos
locales. No muestra eventos ni alertas almacenadas. Permite reintentar la ruta
original, consultar `status.seismik.org` con internet y llamar al 123 en Colombia.

El Worker sirve `/offline.html`, `/offline.css`, `/offline.js`, `/site.js` y
`/sw.js` desde su propio paquete. Para navegaciones HTML GET/HEAD al origen web,
una excepción de red, un timeout de 8 segundos o una respuesta 5xx devuelve el
respaldo con HTTP 503 y `Retry-After: 60`. Las respuestas normales, los 404 y los
contratos de API/OAuth se conservan. Las comprobaciones de estado tienen timeout
de 5 segundos por servicio.

El service worker guarda exclusivamente cuatro archivos públicos del respaldo,
no las páginas visitadas ni respuestas API, sesiones o datos de usuarios. Tras
su instalación en una primera visita en línea, cubre navegaciones sin internet
y caídas 5xx en ese dominio. La instalación necesita HTTPS (o localhost),
JavaScript y almacenamiento permitido. Cada subdominio necesita su propia visita.
No puede cubrir una primera visita sin internet ni una caída de Cloudflare sin
una copia previa. No recarga automáticamente.

## Actualización y publicación

1. Tras editar `web/offline.*`, `web/site.js` o `web/sw.js`, ejecutar
   `python tools/generate_fallback_assets.py`. Genera `deploy/fallback-assets.js`
   y actualiza la versión de caché a partir del contenido del respaldo.
2. Ejecutar `node --test tests/web_fallback.test.mjs` (Node 22 o posterior).
   CI valida que los recursos empaquetados y las dos copias del enrutador coincidan.
3. Publicar la imagen web por el procedimiento habitual y el Worker con el
   `wrangler.toml` de la raíz o el de `edge-worker/`. Ambos incluyen el mismo
   módulo de respaldo. Publicar sólo la imagen web no activa el respaldo del borde.
4. Visitar el dominio con conexión, esperar a que se active el service worker,
   desactivar la red y abrir otra ruta pública. Comprobar texto, estilo y reintento.

Estos cambios no publican ni modifican infraestructura por sí solos.
