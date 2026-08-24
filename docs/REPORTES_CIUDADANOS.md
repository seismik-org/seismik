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

Antes de producción se necesita una política de retención, borrado, acceso,
moderación, antiabuso y cumplimiento jurídico por país. No deben hacerse públicos
reportes individuales ni coordenadas sin agregación y evaluación de privacidad.
