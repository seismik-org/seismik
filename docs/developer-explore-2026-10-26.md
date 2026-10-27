# Explorador de historial para desarrolladores

Publicado en https://devs.seismik.org/explore (también `/explore/`). Comparte estilos, sesión y cuentas del portal. Incluye mapa Leaflet, temas por preferencia del sistema, lista, búsqueda local, período de 1/7/30 días, magnitud mínima, fuentes y hasta 500 resultados por consulta. No implica disponibilidad completa de todos los eventos: se informa si falla una fuente o se alcanza el límite.

## Autorización y consumo

`GET /v1/developer/explore/history` requiere la cookie de sesión existente. No acepta una clave de consumidor o un token Bearer como sustitutos, ni permite seleccionar UID o plan mediante parámetros. Usa la validación de sesión del portal, incluidas las comprobaciones Firebase existentes. Rechaza peticiones de otros sitios antes de consumir cuotas.

El servidor obtiene el UID de la sesión y llama a `consume_developer_account`, el mismo medidor utilizado por las claves de API después de este cambio. No crea, recupera ni envía una clave al navegador. Los límites por minuto/día se comparten por cuenta; la reserva mensual es atómica entre workers y claves. Se conserva la semántica existente de contar intentos en minuto/día y solicitudes admitidas en el medidor mensual. No se habilitan pagos ni débitos nuevos.

Una consulta de historial admitida consume una unidad `events:read`, también al servir datos en caché. Cambiar el plan no reinicia el uso. Los filtros son validados antes de medir. El panel de cuenta no consume consultas de eventos. Mover el mapa, seleccionar un evento y filtrar el conjunto cargado son operaciones locales. No hay polling automático: se realiza una consulta inicial al entrar y otras al pulsar «Consultar historial». Un error de cuota respeta `Retry-After`.

La ruta llama directamente al historial existente con el principal ya autorizado: no utiliza una petición HTTP con credenciales internas ni ejecuta dos veces su dependencia de autorización. Conserva en producción la unificación y campos de magnitud beta actuales. Los detalles muestran `source_reports` cuando existen, sin promediar magnitudes de distintas escalas.

## Datos y seguridad del navegador

- Los candidatos preliminares se incorporan sólo si se marca la opción correspondiente. Se identifican como señales sin confirmar; no se dibujan sus centros de estaciones como epicentros.
- Texto de eventos y nombres mediante `textContent`; enlaces originales admiten sólo HTTPS. Los casos sin magnitud, profundidad o coordenadas no se convierten en ceros.
- Respuestas `/v1/` de devs con `Cache-Control: no-store`; la respuesta de historial incluye `Vary: Cookie`. El frontend usa `credentials: same-origin` y `cache: no-store`.
- CSP del explorador sólo admite scripts/estilos propios y las imágenes de mapas de `tile.openstreetmap.org`. No relaja las otras páginas. Referrer `strict-origin-when-cross-origin` en el HTML para cumplir las condiciones del proveedor de mapas; no se envían cookies de Seismik a ese dominio.
- Leaflet 1.9.4 se sirve localmente, con licencia BSD incluida. Se comprobaron los SHA-256 publicados por Leaflet para JS/CSS. Los mosaicos se solicitan sólo para la vista actual y respetan la caché normal del navegador. No hay descarga masiva ni mapas offline. OSM es un proveedor externo sin SLA.
- El explorador usa `noindex`; no publica perfiles o consumos para motores de búsqueda. Cerrar sesión borra los datos visibles; restaurar desde bfcache comprueba otra vez la sesión sin repetir la consulta automáticamente.

## Verificación

- Suite Python: 723 pruebas correctas, incluidos casos nuevos de sesión obligatoria, aislamiento de cuenta, cuota compartida con claves, concurrencia mensual, cambio de plan, parámetros inválidos, origen cruzado y sesión borrada.
- `ruff src tests` y `mypy src` correctos.
- 15 pruebas Node del borde y páginas existentes correctas.
- `tools/check_explore_browser.py`: Chrome con fixtures locales y mapas simulados; temas claro/oscuro, móvil sin desbordamiento, dos magnitudes de agencia, XSS tratado como texto, coordenadas nulas, filtros locales sin más consultas, resultados vacíos, fallo parcial, 429 y cierre de sesión. Las capturas de esta prueba no son datos sísmicos reales.
- Producción: `/explore`, `/explore/`, `/explore.html`, JS y Leaflet devuelven 200; CSP y política de referrer verificadas. El endpoint sin sesión devuelve 401 y `no-store`. La salud autenticada de la API devuelve 200. Chrome mostró la página publicada con su acceso cerrado hasta iniciar sesión. No se inició sesión en nombre del usuario ni se leyó su consumo real para estas comprobaciones.

## Despliegue

Se usaron parches sobre los digests exactos de API y web; no se reconstruyó desde main, que no contiene todos los cambios manuales de producción. Sólo se añadieron dos archivos Python y ocho recursos web. El Worker se descargó como respaldo y se modificaron dos puntos de enrutamiento/cabeceras, preservando el resto del módulo, D1 y el secreto de origen. Detector, dispatcher, forwarder y Waves no cambiaron.

| Componente | Nueva revisión / versión | Anterior |
| --- | --- | --- |
| API | `seismik-api-00065-dr7` | `seismik-api-00064-w47` |
| Web | `seismik-web-00063-vrd` | `seismik-web-00062-gbv` |
| Worker seismik | `8cf55353-5061-490e-91c4-f6ec5bce0cd6` | respaldo local del módulo, SHA-256 `c3b4ca741a06bbd54f174edfa480fa05c3fa5bbd24f5ab587cdfbd3915d378df` |

Cloud Build API `4b399d4b-1ffb-4f27-9e5d-168e6b567a2c`; web `a10175db-2d00-4f27-a81b-f05bfcd125c3`; ambos SUCCESS. Contextos limitados a 31,9 KiB y 248,7 KiB; ningún archivo de credenciales.

Contextos y respaldo local: `work/deploy-developer-explore-20261026`. Evidencia y scripts de preparación: `work/audits/developer-explore-20261026`. No contienen valores de credenciales. Las lecturas temporales de credenciales se mantuvieron en memoria.

Reversión, proyecto `seismik-15bbb`, región `us-east1`:

```powershell
gcloud run services update-traffic seismik-api --project=seismik-15bbb --region=us-east1 --to-revisions=seismik-api-00064-w47=100
gcloud run services update-traffic seismik-web --project=seismik-15bbb --region=us-east1 --to-revisions=seismik-web-00062-gbv=100
```

Si se revierte la función, restaurar también el módulo Worker respaldado mediante Wrangler conservando los bindings. No hacer push a main a ciegas: su CD podría sustituir cambios manuales anteriores de producción.
