# Versión 71 publicada en prueba interna

El 2 de noviembre de 2026 el usuario autorizó expresamente desplegar la API y publicar la app. Este estado sustituye la retención inicial descrita en `mobile-family-v71-prepared-2026-11-02.md`.

## API

Proyecto `seismik-15bbb`, región `us-east1`, servicio `seismik-api`. Revisión activa `seismik-api-family-v71-1102`, con el 100 % del tráfico.

Imagen: `us-east1-docker.pkg.dev/seismik-15bbb/seismik/api@sha256:3e6298ea059471c280b6c02f53951ca0696c895d31d0f48003125236b2e93744`.

Primero se creó sin tráfico con la etiqueta `family-v71-review`. Cloud Run confirmó Ready y ContainerHealthy. Se comparó la especificación completa de ejecución con el respaldo anterior, normalizando únicamente la imagen: idéntica. Se comprobaron además las anotaciones de ejecución/escalado existentes. Se conservaron variables, referencias de secretos, identidad de servicio, red, recursos, sondas y escalado. No se cambiaron IAM, DNS, web, detector ni dispatcher.

Antes y después de activar tráfico: `/health/live` y `/health/ready` devolvieron 200; Redis respondió. La lectura familiar privada sin sesión devolvió 401. `/v1/liveahora/events` devolvió 200. La primera lectura directa de readiness devolvió el 403 esperado de la guardia de origen; las comprobaciones posteriores usaron la credencial existente sólo en memoria, sin imprimirla ni cambiarla.

Comprobaciones públicas posteriores:

- `https://api.seismik.org/health/ready`: 200.
- `https://api.seismik.org/v1/family/messages?sender_id=0000000000000000&recipient_id=1111111111111111`: 401.
- `https://liveahora.seismik.org/v1/liveahora/events`: 200.
- `https://status.seismik.org/api/status`: 200, API/web/developers disponibles.

Respaldo privado y comprobaciones, en Cloud Shell: `~/seismik-family-v71-20261102/`, archivos `api-predeploy.json`, `api-staged.json`, `api-active.json`, `staging-checks.json`, `active-checks.json`, `check-release.py`. No copiar las configuraciones privadas al repositorio.

Reversión si se detecta una regresión: devolver el 100 % del tráfico a la revisión preservada `seismik-api-showcase-agencies-1102` con `gcloud run services update-traffic seismik-api --project=seismik-15bbb --region=us-east1 --to-revisions=seismik-api-showcase-agencies-1102=100`. No borrar ni sustituir datos Redis.

## Google Play

App existente `com.seismik.app`, cuenta de desarrollador `5234527400533769157`, app `4973936615854647264`. Se publicó en la pista interna existente `4701297958425543883`, lanzamiento 12: **71 - Familia y conexión**. Play Console confirmó «Activo», «Versión más reciente: 71 - Familia y conexión» y «Disponible para verificadores internos». Fecha mostrada: 2 nov 2026, 8:51 p. m. (Colombia). No se promovió a prueba cerrada ni producción pública.

El paquete aceptado es `1.0.0+71`, firmado con la clave original recuperada. AAB SHA256 `c3faa0c7ccf24f5c1cf9d6c66d5a2861ba1b09c122a528f1dbee93d1a8ceab55`. Google aceptó certificado y código de versión; sin pérdida de dispositivos compatibles frente a la versión interna 69. Se mantuvieron los verificadores existentes. La disponibilidad en cada dispositivo puede tardar en propagarse; no se comprobó una instalación real.

Las pruebas previas cubren 196 casos Flutter y 796 Python, más análisis Flutter, Ruff y mypy. Las comprobaciones de producción son de lectura y protección de acceso; no se enviaron mensajes reales a familiares ni se acreditó entrega con dos cuentas físicas. No se modificó el iPhone nativo.

Comprobantes locales en `C:\Users\LENOVO\Documents\Codex\2026-10-31\ab\outputs`: `api-v71-desplegada.png`, `play-v71-publicada-interna.png`, `SEISMIK-APP-V71-PREPARADA.md`.
