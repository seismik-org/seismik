# Reporte web «¿Lo sentiste?»

La web se publica en `https://ifeltit.seismik.org/`. Usa el stream
`SEISMIK_FELT_REPORTS_STREAM` de los reportes voluntarios de la app, con
`source=web`, `device_id=web-unverified` e `integrity_verified=false`. No registra
dispositivos ni evita la atestación de `/v1/reports/felt`. Los consumidores deben
conservar esta procedencia y no interpretar un reporte web como un dispositivo
verificado. `report_id` conserva el UUID del formulario; el `event_id` del bus
lleva el prefijo `web:` para evitar colisiones con los IDs móviles. La ventana
de deduplicación es la existente (`SEISMIK_WEBHOOK_IDEMPOTENCY_SECONDS`).

El formulario tiene tres pasos. Duración, movimiento, actividad, tipo y altura
del edificio, piso, reacción, otras personas, ruido, ventanas, lámparas y muebles
son opcionales. Por defecto el servidor redondea las coordenadas a dos decimales
y elimina `location_accuracy_m`; la ubicación exacta requiere una elección.
No recoge nombre, correo ni archivos. Tampoco permite comentarios libres.
Los enlaces oficiales se muestran después del envío si el visitante los elige:
ningún organismo recibe información hasta que complete su formulario externo.

Las respuestas se conservan en memoria después de un fallo de red y se reutiliza
el identificador al reintentar sin cambios. Cualquier edición crea otro ID.
Cerrar o recargar la pestaña pierde las respuestas. Sólo un 202 con aceptación
o duplicado del mismo `report_id` confirma el envío. Cada reintento con Turnstile
requiere una nueva verificación; el token nunca se publica en el stream.

## Activación en producción

1. Desplegar API y web mediante los jobs existentes `deploy-api` y `deploy-web`
   de `.github/workflows/ci.yml`. La API incluye `/v1/reports/web/config` y
   `/v1/reports/web/felt`; `Dockerfile.web` incluye `web/ifeltit.*` y versiona
   sus recursos. Los despliegues manuales usan `deploy/cloudbuild.api.yaml`
   y `deploy/cloudbuild.worker.yaml` con `_DOCKERFILE=Dockerfile.web`, seguidos
   de `gcloud run services update` de cada servicio. Usar `--update-env-vars`
   y `--update-secrets` para conservar la configuración existente.
2. Autorizar `ifeltit.seismik.org` en el widget Turnstile existente.
   Configurar `SEISMIK_TURNSTILE_SITE_KEY` y `SEISMIK_TURNSTILE_SECRET_KEY` en
   la API; almacenar la clave secreta en Secret Manager. Configurar
   `SEISMIK_FELT_WEB_HOSTNAME=ifeltit.seismik.org`. El servidor exige la
   acción `felt_report` y ese hostname. Fuera de development, la falta de
   cualquiera de las dos claves produce 503. El endpoint config publica
   únicamente la clave pública y el estado de disponibilidad.
3. Crear el registro DNS proxied y la ruta del Worker
   `ifeltit.seismik.org/*`. Verificar el certificado activo para
   `*.seismik.org`, que cubre este hostname de un nivel. No contratar ACM
   ni utilizar `ifeltit.api.seismik.org`: ese hostname anidado necesitaría
   cobertura adicional.
4. Publicar `deploy/cloudflare-edge-router.js` (idéntico a
   `edge-worker/worker.js`) con sus imports. El Worker sirve `/` desde
   `/ifeltit.html`, dirige `/v1/reports/*` a la API y habilita geolocalización
   sólo para este host. Conservar iguales `EDGE_ORIGIN_SECRET` del Worker y
   `SEISMIK_EDGE_ORIGIN_SECRET` de la API, con una versión fija al rotarlos.
   El Worker reemplaza `X-Seismik-Client-IP` por `CF-Connecting-IP`; sólo la
   guardia autenticada habilita su uso en el backend. Redis conserva únicamente
   el hash de la IP en claves de límite con vencimiento de 120 segundos; la IP
   no forma parte del reporte. Los Caddy alternativos también incluyen el host;
   envían la IP del par de conexión, no cabeceras arbitrarias del visitante.
5. Comprobar HTTPS y el certificado del hostname, configuración pública,
   Turnstile real, un POST aceptado con 202 y lectura del stream autorizado.
   Repetir el mismo `report_id` dentro de la ventana de deduplicación con un
   token Turnstile nuevo: debe responder `duplicate=true` sin un segundo
   registro. Comprobar `source`, `device_id`, `integrity_verified`, ubicación
   redondeada y ausencia de `turnstile_token`. Probar también ubicación exacta
   elegida, token inválido y acceso directo al origen sin su secreto (403).

## Verificación local

```bash
python -m pytest tests/test_web_reporting.py tests/test_reporting.py tests/test_web_hardening.py tests/test_web_assets.py
node --test tests/web_fallback.test.mjs
```

Para probar la interfaz con la API bajo el mismo origen, configurar Redis de
desarrollo mediante `SEISMIK_REDIS_URL`, `SEISMIK_ENVIRONMENT=development` y
ejecutar `python tools/serve_ifeltit.py`. Abrir `http://127.0.0.1:8080` o
`http://localhost:8080`. Se omite Turnstile sólo si ambas claves están vacías;
con una sola clave, también development falla cerrado. No usar el servidor
local para producción. Las verificaciones locales no certifican DNS, TLS ni
Turnstile reales.
