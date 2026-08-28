# Seismik — cierre técnico Sprint 3

Versión: 1.0  
Fecha de corte: 2026-08-27 (America/Bogota)  
Resultado: objetivo técnico alcanzado; **No-Go para alertas públicas**

## Objetivo alcanzado

El backend integrado procesa un caso MiniSEED histórico, produce un candidato,
lo ingiere mediante webhook HMAC, lo conserva en Redis Streams y permite que el
dispatcher genere una notificación crítica de prueba. Todo el recorrido se ejecutó
con API, Redis y dispatcher reales bajo Docker Compose.

## Resultado por actividad

| ID | Estado | Resultado |
|---|---|---|
| S3-01 | CO | Contratos Pydantic v2 y OpenAPI estrictos |
| S3-02 | CO | HMAC, ventana antirreplay, límite de cuerpo e idempotencia |
| S3-03 | CO técnico | Redis Streams, consumer groups y DLQ documentados por ADR |
| S3-04 | CO técnico | Registro tipado con App Check y validación segura de producción |
| S3-05 | CO | `dry_run` auditable; envío externo desactivado |
| S3-06 | CO | E2E Docker real aprobado |
| S3-07 | CO técnico | Guardrails y configuración sin crear recursos cloud |

## Evidencia E2E

Archivo canónico: `docs/evidence/sprint3-docker-e2e.json`.

- Caso: `co-2023-08-17-m6.1`.
- SHA-256 MiniSEED: `307eb2e655680918d097274d96cae67087332198e24034f05cbaf16ada905f48`.
- Primer webhook aceptado y publicado en Stream.
- Segundo webhook idéntico reconocido como duplicado, sin nueva publicación.
- Dispatcher generó un payload crítico `TEST` con texto UTF-8 correcto.
- Cero llamadas APNs/FCM y cero tokens guardados en la evidencia.
- El dispositivo efímero de la prueba fue dado de baja al finalizar.

## Validación

- Backend: 55 pruebas aprobadas.
- Ruff: sin hallazgos.
- mypy: sin hallazgos en los archivos fuente.
- API y Redis publicados solo en loopback durante la prueba.
- Redis con AOF habilitado y servicios saludables.
- GCP y facturación: no activados.

## Límites y decisión

Este cierre valida integración de software, no exactitud sismológica ni
operación de emergencia. Continúan pendientes la revisión científica, pruebas en
dispositivos Android reales, operación en sombra, observabilidad y revisión legal.
Por ello se autoriza avanzar al Sprint 4, pero se mantiene prohibido emitir
alertas públicas automáticas.
