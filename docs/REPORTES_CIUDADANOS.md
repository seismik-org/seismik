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

## admin.seismik.org

Panel interno con tres pestañas: **Resumen** (cuentas, dispositivos, claves y
sesiones contadas en Redis; entradas totales, de 24 h y de 7 días de cada stream),
**Reportes** (app y web con su sismo, distancia, plausibilidad recalculada al
consultar y revisión) y **Registros** (últimas entradas de cada stream permitido,
con tokens, firmas, secretos e IP ocultos por la API). Entran sólo los correos de
`SEISMIK_ADMIN_EMAILS` (separados por comas, variable del servicio `seismik-api`
en Cloud Run) con la sesión de auth.seismik.org; sin la variable responde 403 a
todos. «Iniciar sesión» deja la cookie `seismik_after_login=admin` (10 minutos)
y `_finish_login` vuelve a `admin_portal_url` en lugar del portal de
desarrolladores. El Worker enruta `admin.seismik.org/v1/*` a la API y `/` a
`web/admin/`; necesita el registro DNS proxied y la ruta `admin.seismik.org/*`
del Worker `seismik`. API: `GET /v1/admin/me`, `/v1/admin/overview`,
`/v1/admin/records/{nombre}`.

En producción, la API exige además la guardia de origen autenticada y la
cabecera del host admin que el Worker reemplaza; no acepta la suministrada por
el visitante. La sesión debe haberse iniciado en las últimas ocho horas y se
limita a 120 consultas por minuto. Las revisiones exigen `Origin` del panel y
`X-Seismik-Admin: 1` contra CSRF, incluidos otros subdominios. Cada revisión y
su deshacer dejan una entrada de auditoría. Los CSV neutralizan fórmulas; la
API oculta también credenciales anidadas en los reportes. Al salir se limpian
las tablas y al volver desde el historial se comprueba otra vez el acceso.

La revisión de reportes: Marcar un reporte como válido o descartado lo guarda
en el hash `seismik:reports:review` con el correo y la fecha; el reporte original
no se modifica ni se borra del stream. API: `GET /v1/reports/admin/reports` y
`POST /v1/reports/admin/reports/{felt|damage}/{stream_id}/review`.

Antes de producción se necesita una política de retención, borrado, acceso,
moderación, antiabuso y cumplimiento jurídico por país. No deben hacerse públicos
reportes individuales ni coordenadas sin agregación y evaluación de privacidad.
