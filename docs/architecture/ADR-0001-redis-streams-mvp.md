# ADR-0001 — Redis Streams como bus durable del MVP

Estado: aceptada para ambiente local y beta cerrada  
Fecha: 2026-08-26  
Revisión obligatoria: antes de producción pública o más de una región

## Contexto

Seismik necesita una cola durable entre la ingesta FastAPI y el dispatcher. Ya
usa Redis para dispositivos, geocercas, cooldown, idempotencia y clustering H3.
Las opciones evaluadas para el bus fueron Redis Streams y Google Pub/Sub.

## Decisión

Usar Redis Streams durante el MVP. El API publica mediante una operación atómica
idempotente; el dispatcher usa consumer groups, recuperación de pendientes,
reintentos limitados y dead-letter stream. Redis debe tener AOF habilitado.

## Motivos

- Permite ejecutar todo localmente y no obliga a activar GCP.
- Evita operar Redis y Pub/Sub simultáneamente durante una beta pequeña.
- Mantiene baja latencia y reutiliza una dependencia que el producto ya necesita.
- El contrato de evento no depende de Redis y permite migrar posteriormente.

## Límites y consecuencias

- Redis standalone es un punto único de falla. Es aceptable solo para desarrollo
  y beta cerrada, no para alerta pública.
- `MAXLEN ~ 100000` limita memoria, pero también la retención; la evidencia de
  largo plazo debe exportarse a almacenamiento separado.
- El Lua de H3 toca varias celdas y no es compatible directamente con Redis
  Cluster cuando las claves caen en slots distintos.
- Pub/Sub deberá reevaluarse si se requiere retención independiente, múltiples
  regiones, varios equipos consumidores o tolerancia a pérdida regional.

## Seguridad y operación

- Streams: `stream:seismik:candidates`, `stream:seismik:official` y
  `stream:seismik:dead-letter`.
- El modo sombra escribe intentos en `stream:seismik:push-test`; nunca contiene
  tokens APNs/FCM.
- Push externo solo puede habilitarse en modo `testers` con allowlist explícita,
  o en modo `production` dentro de un ambiente declarado como producción.
- La migración a Pub/Sub conservará los esquemas OpenAPI y `event_id` como clave
  de idempotencia; se implementará detrás de la interfaz del bus.
