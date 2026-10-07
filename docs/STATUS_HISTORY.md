# Historial público de disponibilidad

La base Cloudflare D1 existente `seismik-status` conserva la tabla `probes`
con columnas `minute`, `api`, `web` y `developers`. No recrear ni vaciar esta
base. El historial se añadió en un despliegue manual de Wrangler que quedó
fuera de Git; un despliegue posterior del repositorio reemplazó su código y
el binding D1, aunque conservó los registros y el cron.

Ambos `wrangler.toml` declaran ahora `STATUS_DB` y el cron de cada minuto.
`scheduled` registra el resultado sin depender de visitas. Un reintento no
sobrescribe una muestra existente. `/api/history` agrupa los últimos 30 días
en UTC, incluyendo días sin muestras como desconocidos. El porcentaje de la
página describe comprobaciones exitosas, no disponibilidad durante huecos.
No se eliminan registros anteriores.

La página y sus scripts se empaquetan en el Worker para que el historial sea
accesible aunque el origen web no responda. Después de editar `web/status.*`:

```powershell
node tools/generate_status_assets.mjs
node --test tests/web_fallback.test.mjs tests/email_auth.test.mjs tests/status_history.test.mjs
```

Publicar el Worker del repositorio mediante el build de Cloudflare en `main`.
Comprobar `/api/history`, la página pública y que la última muestra avance
tras el siguiente minuto. Los secretos de origen continúan administrados en
Cloudflare y no forman parte de la base ni de las respuestas públicas.
