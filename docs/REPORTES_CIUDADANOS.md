# Reportes ciudadanos y agencias oficiales

Seismik admite dos reportes firmados:

- `POST /v1/reports/felt`: percepción e intensidad MMI estimada.
- `POST /v1/reports/damage`: severidad, peligros, heridos o atrapados.

Ambos exigen un dispositivo registrado, `X-Seismik-Timestamp` y
`X-Seismik-Signature`. Se almacenan en Streams separados, tienen rate limiting e
idempotencia por `report_id`. La ubicación es aproximada por defecto: el backend
redondea latitud y longitud a dos decimales y elimina la precisión del sensor.

Si la persona da consentimiento, la respuesta ofrece enlaces a formularios del
SGC (Colombia), IGN (España), NRCan (Canadá) y USGS DYFI (global). Son formularios
externos: Seismik no simula una integración ni los envía automáticamente. La app
explica esto antes de abrir el navegador.

Un reporte de daños no es una solicitud de rescate. Heridos, atrapados, incendio,
fuga de gas, colapso o peligro inmediato activan una advertencia para contactar a
los servicios locales de emergencia.

## Plausibilidad y revisión

Cada reporte (app, web y daños) guarda `plausibility`, calculada en
`src/reporting/plausibility.py` con el sismo indicado: distancia al epicentro,
radio en el que suele sentirse (`10^(0.42·M + 0.2)` km) e intensidad esperada
(`1 + 1,5·M − 3·log10(distancia hipocentral)`). Es `implausible` si alguien dice
haberlo sentido a más del doble de ese radio, si la intensidad supera la esperada
en más de 3 grados o si la hora es anterior al sismo; `unknown` si no hay sismo
del catálogo con el que comparar. Es orientativa y nunca rechaza un envío.

`https://devs.seismik.org/reportes/` lista los reportes de ambos orígenes con su
sismo, distancia, plausibilidad (recalculada al consultar) y revisión. Entran sólo
los correos de `SEISMIK_REPORT_ADMIN_EMAILS` (separados por comas, variable del
servicio `seismik-api` en Cloud Run) con la sesión del portal; sin la variable el
panel responde 403 a todos. Marcar un reporte como válido o descartado lo guarda
en el hash `seismik:reports:review` con el correo y la fecha; el reporte original
no se modifica ni se borra del stream. API: `GET /v1/reports/admin/reports` y
`POST /v1/reports/admin/reports/{felt|damage}/{stream_id}/review`.

Antes de producción se necesita una política de retención, borrado, acceso,
moderación, antiabuso y cumplimiento jurídico por país. No deben hacerse públicos
reportes individuales ni coordenadas sin agregación y evaluación de privacidad.
