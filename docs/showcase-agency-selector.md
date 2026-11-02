# Una tarjeta por sismo y selector de agencia — 2026-11-02

La sección «Últimos sismos reportados por agencias oficiales» de https://seismik.org/#asi-se-ve reúne reportes coincidentes en una tarjeta. Cuando hay varias agencias, el selector actualiza magnitud y escala, lugar, hora, profundidad, fuente oficial y el enlace de «¿Lo sentiste?». Cada opción conserva los valores originales publicados por su agencia.

## Asociación y datos

Se reutiliza api.event_association: coincidencia de hora de origen hasta 45 segundos, distancia hasta 40 km y diferencia de profundidad hasta 60 km cuando ambas están disponibles. Todos los integrantes del grupo deben ser compatibles entre sí y proceder de fuentes distintas. Los componentes ambiguos, las réplicas próximas, los reportes sin evidencia suficiente y los candidatos preliminares permanecen separados.

En esta presentación se consolidan también identificadores de un mismo catálogo con solución exactamente idéntica: hora, coordenadas, profundidad, magnitud y escala. Los identificadores originales se conservan en related_event_ids. Esto resuelve el caso observado de dos identificadores INGV para Creta sin relajar la separación de eventos ambiguos.

La API consolida primero revisiones y aliases, agrupa las agencias y aplica después el límite de tarjetas. Basta con que una agencia supere la magnitud mínima; las estimaciones inferiores de las otras fuentes permanecen seleccionables. La opción inicial supera el umbral y sigue la prioridad existente SGC/USGS/EMSC. No se calcula una magnitud promedio.

GET /v1/public/showcase-events conserva los campos principales y añade source_reports (los mismos campos públicos por fuente), related_event_ids y association_method. GeoJSON conserva los reportes en properties. Estos campos pasan por una lista explícita de campos públicos. No se escribe ni se modifica el stream oficial.

## Publicación preservada

Código: 9c8773d, rama feature/showcase-agency-selector, subida a GitHub. Cloud Build us-east1 47e5d78f-676c-48f5-b6ea-7bc4c2e8df11, SUCCESS.

| Servicio | Revisión activa | Tráfico | Imagen |
|---|---|---|---|
| seismik-api | seismik-api-showcase-agencies-1102 | 100 % | sha256:dcb243856af3f897bbf537e1ee44a55bcb4861644daedaed945e14dd633c2727 |
| seismik-web | seismik-web-showcase-agencies-1102 | 100 % | sha256:efb2d94964b5a970cf1264635d3aedf9cf4d5d3af1d89d2cfa39a458fd9b10fe |

Proyecto seismik-15bbb, región us-east1. Las bases son los digests activos anteriores de API y web. El build comprueba hashes de public.py, event_association.py, showcase.js y home.css antes de usar los archivos. En index.html modifica el párrafo mediante contexto comprobado y versiona las dos referencias de assets. Los otros archivos de las imágenes existentes se conservan.

Se compararon las especificaciones de ejecución de las revisiones aisladas con las originales: variables y referencias de secretos, identidad, recursos, sondas, volúmenes y límites de escala conservados. Las funciones de cuenta, correo y LiveAhora siguen en sus imágenes base. Los servicios sísmicos, DNS, IAM, Firestore y Cloudflare no se cambiaron en esta publicación.

Revisiones anteriores conservadas: seismik-api-review-fixes-1102 y seismik-web-family-1101-final. Para revertir el servicio correspondiente, tras comprobar el estado actual:

    gcloud run services update-traffic SERVICIO --to-revisions=REVISION_ANTERIOR=100 --project=seismik-15bbb --region=us-east1

## Verificación

- 792 pruebas Python correctas; 62 pruebas Node correctas; Ruff y mypy sin incidencias (95 módulos).
- Casos nuevos: varias agencias por tarjeta, límite después de agrupar, alias idénticos de INGV, ambigüedad entre réplicas, agencias con magnitud inferior al umbral, GeoJSON, privacidad de campos y cambio de datos/enlaces mediante el selector.
- En staging real: 11 reportes representados en cuatro tarjetas, con 2/3/2/3 fuentes. Los hashes de JS/CSS servidos coinciden con los compilados. Liveness/readiness de API, cronograma público, rechazo del panel y sesión sin autenticación, y páginas de cuenta, LiveAhora y Grupo comprobados.
- En el navegador integrado de producción: cuatro tarjetas, selección de EMSC para Creta y de IGP para Perú. Creta cambia de 5.3 mb/48.525 km (USGS) a 5.1 m/24 km (EMSC); Perú cambia de 5.1 mb/67.239 km (USGS) a 5.0/30 km (IGP), con sus respectivos enlaces oficiales.

Los recuentos y datos anteriores son la muestra observada durante la comprobación; el catálogo continúa actualizándose. La asociación es una presentación conservadora de reportes oficiales y no acredita validación del detector o de alertas tempranas.

Los archivos exactos de construcción y su manifiesto SHA-256 se guardan en outputs/showcase-agencies-build-20261102 del chat de trabajo; la captura pública está en outputs/showcase-agencias-publicado-20261102.png. La configuración completa de GCP permanece privada en Cloud Shell.
