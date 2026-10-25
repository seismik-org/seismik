# Revisión de detecciones SeedLink — 24 de octubre de 2026

## Resultado

De los 12 candidatos colombianos que produjeron avisos personales de diagnóstico, cuatro son compatibles con sismos colombianos de catálogo, cuatro con ondas de sismos lejanos y cuatro quedan sin confirmar. No hay evidencia suficiente para llamar a estos últimos «ruido» o «sismos falsos». La coincidencia de llegadas tampoco constituye validación científica del detector ni de su magnitud beta.

| Aviso (hora de Bogotá) | Resultado retrospectivo | Magnitud de catálogo | Fuente |
| --- | --- | --- | --- |
| 17 oct., 18:27 | Compatible: Pijiño del Carmen, Magdalena | 2.1 | [SGC2026umhmmg](https://www.sgc.gov.co/detallesismo/SGC2026umhmmg/resumen) |
| 18 oct., 10:24 | Compatible: El Carmen, Santander | 3.4 | [SGC2026unnete](https://www.sgc.gov.co/detallesismo/SGC2026unnete/resumen) |
| 19 oct., 03:08 | Compatible con ondas de Vanuatu; no epicentro colombiano | 6.0 | [us6000u3bc](https://earthquake.usgs.gov/earthquakes/eventpage/us6000u3bc) |
| 19 oct., 15:37 | Sin confirmar | — | Sin explicación suficiente en las ventanas revisadas |
| 20 oct., 17:00 | Compatible: Los Santos, Santander | 3.2 | [SGC2026urrudm](https://www.sgc.gov.co/detallesismo/SGC2026urrudm/resumen) |
| 20 oct., 20:22 | Sin confirmar; la coincidencia con Zona Bananera no explica las estaciones | — | Asociación descartada por tiempos de llegada |
| 22 oct., 09:53 | Compatible con ondas de China; no epicentro colombiano | 7.0 | [us6000u43g](https://earthquake.usgs.gov/earthquakes/eventpage/us6000u43g) |
| 22 oct., 21:13 | Compatible: Los Santos, Santander | 3.5 | [SGC2026uvrpmm](https://www.sgc.gov.co/detallesismo/SGC2026uvrpmm/resumen) |
| 23 oct., 23:31 | Compatible con ondas de Vanuatu; no epicentro colombiano | 5.8 | [us6000u4jw](https://earthquake.usgs.gov/earthquakes/eventpage/us6000u4jw) |
| 24 oct., 15:50 | Sin confirmar; Los Santos M1.8 no explica el conjunto de estaciones | — | Dos picos preceden la llegada P prevista por unos 43–46 s |
| 24 oct., 21:27 | Compatible con ondas de Bonin/Japón; no epicentro colombiano | 6.5 | [us6000u4r9](https://earthquake.usgs.gov/earthquakes/eventpage/us6000u4r9) |
| 24 oct., 21:30 | Sin confirmar | — | No se estableció una explicación por las fases examinadas |

Las magnitudes de la tabla pertenecen a los catálogos, no son resultados de la ML de Seismik. Los tiempos son los de detección, no los de origen.

## Alcance y evidencia

Ventana UTC: 2026-10-17T16:27:52Z a 2026-10-25T02:42:01.119371Z. Se paginaron completamente 2.497 registros de logs: 761 candidatos únicos (749 de Chile y 12 de Colombia). Los 12 avisos estudiados tienen aceptación del proveedor de push; esto no prueba que el teléfono los haya recibido, reproducido o leído. Ninguno de esos 12 tenía una actualización oficial asociada en los logs.

Se contrastaron 755 eventos del SGC, 520 de EMSC, 20 de USGS en las regiones examinadas, 307 del CSN de Chile y 190 eventos globales USGS de M ≥ 4.5. Las 118 coincidencias temporales/regionales del conjunto de 761 no equivalen a confirmaciones. Los otros 643 tampoco constituyen falsos positivos demostrados.

Se recuperaron 36 ventanas de ondas desde EarthScope (tres estaciones por aviso, 1.115.648 bytes); sus picos STA/LTA reproducen los disparos registrados. El contraste de fases utilizó IASP91. Los cuatro casos lejanos son compatibles con PKIKP. Sus aproximadamente 18–20 minutos de propagación física no son latencia de Internet; el retraso de los paquetes de disparo estudiados fue aproximadamente 2–14,5 s.

Los casos colombianos combinan picos compatibles con P y S: no son cuatro demostraciones de detección temprana basada exclusivamente en P. Los modelos globales y los picos STA/LTA tienen limitaciones; no se ha calibrado aquí un clasificador de teleseísmos ni un porcentaje de precisión operacional.

El último origen disponible en el catálogo SGC consultado era 2026-10-25T01:34:19Z, anterior a los dos avisos más recientes. Esa demora refuerza la clasificación pendiente de los casos sin explicación. En producción se observaron respuestas HTTP 403 del SGC, incluida una a las 02:28:13Z. La consulta de auditoría sí obtuvo HTTP 200; no se eludió el bloqueo de producción.

Fuentes: [catálogo SGC](https://api.sgc.gov.co/biweekly/biweekly_earthquakes), [USGS FDSN](https://earthquake.usgs.gov/fdsnws/event/1/), [EMSC FDSN](https://www.seismicportal.eu/fdsnws/event/1/), [CSN Chile](https://www.sismologia.cl/).

## Correcciones implementadas

1. La API deja de publicar el centro de las estaciones que dispararon como latitud/longitud del epicentro. Los candidatos sin solución confirmada llevan coordenadas y profundidad nulas, `location_method=unlocated`, `confirmation_status=unconfirmed` y `time_reference=detection_not_origin`. El centro de estaciones se conserva separado con `is_epicenter=false`. Esto corrige también los candidatos ya almacenados al consultarlos, sin modificar sus registros originales.
2. La asociación retrospectiva con un catálogo exige que todas las estaciones independientes del quórum tengan picos compatibles con llegadas calculadas. Se rechazan asociaciones basadas solamente en proximidad temporal y centro de estaciones, así como evidencia incompleta. El margen de 15 s es una compuerta conservadora de consistencia, no validación científica. No se identifican artificialmente los picos como primeras llegadas P.
3. Se conservaron los avisos personales de diagnóstico, la política de alertas críticas, las estaciones, la configuración y la magnitud beta. La evaluación de ML continúa en `failed_validation`. No se desplegó un clasificador automático de teleseísmos ni se convirtió ningún candidato de esta revisión en alerta pública confirmada.

La corrección de presentación se aplica desde la API sin exigir una nueva versión móvil. La revisión retrospectiva de los ocho casos compatibles no se reinyectó como eventos ni alteró las alertas históricas.

## Pruebas y despliegue

- Suite del repositorio: 731 pruebas; `ruff src tests` y `mypy src` correctos.
- Fuentes exactas de producción con el parche: 35 pruebas de API y 29 del detector correctas.
- Cloud Build API: `5f05879f-9425-451c-9cfd-a1b1b02660a8`.
- Cloud Build detector: `035b8f3b-080f-42f9-b4a9-033f72088dc4`.
- API: `seismik-api-00064-w47`, 100 % del tráfico.
- Detector: `seismik-detector-00007-2b4`, 100 % del tráfico.
- Consulta autenticada de 500 candidatos: coordenadas del epicentro nulas, centro separado y campos de magnitud conservados. Salud API y detector comprobadas por separado.

Se construyeron parches sobre los digests exactos desplegados, conservando la ML beta y los cambios previos de producción ausentes de main. Dispatcher y forwarder no se reconstruyeron. No se hizo push a main para evitar que CD sobrescriba esos cambios previos.

Reversión (proyecto `seismik-15bbb`, región `us-east1`):

```powershell
gcloud run services update-traffic seismik-api --project=seismik-15bbb --region=us-east1 --to-revisions=seismik-api-00063-qzd=100
gcloud run services update-traffic seismik-detector --project=seismik-15bbb --region=us-east1 --to-revisions=seismik-detector-00006-qrc=100
```

## Obstáculos pendientes

Hace falta resolver el acceso autorizado al catálogo SGC desde producción, mejorar la separación de fases y teleseísmos y evaluar ruido y sensibilidad regional con una muestra independiente amplia. Estas correcciones eliminan ubicaciones engañosas y asociaciones incompatibles; no convierten el detector actual en un sistema validado de alerta temprana para la población.
