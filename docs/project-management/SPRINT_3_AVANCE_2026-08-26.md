# Seismik — avance técnico Sprint 3

> Documento histórico. El impedimento descrito aquí fue resuelto y el cierre
> vigente está en `SPRINT_3_CIERRE_TECNICO_2026-08-27.md`.

Versión: 0.1  
Fecha de corte: 2026-08-26 (America/Bogota)  
Estado: seis actividades técnicamente listas; E2E Compose pendiente

## Resultado actual

| ID | Estado | Resultado |
|---|---|---|
| S3-01 | CO | Candidate y official-update estrictos, tiempos con zona e invariantes; OpenAPI exportada |
| S3-02 | CO | HMAC exacto, límite 64 KiB, replay temporal, body alterado e idempotencia probados |
| S3-03 | CO técnico | Redis Streams elegido mediante ADR; reevaluación antes de producción pública |
| S3-04 | CO técnico | App Check obligatorio por plataforma; rechazo remoto y producción segura probados |
| S3-05 | CO | Push externo apagado; dry run auditable; testers requieren allowlist |
| S3-06 | ER | MiniSEED → candidato → webhook → Stream → consumer → payload TEST aprobado en memoria |
| S3-07 | CO técnico | Límites y gate de despliegue documentados; cero recursos cloud creados |

## E2E automatizado aprobado

La prueba `tests/test_e2e_pipeline.py` genera MiniSEED impulsivo para tres
estaciones, ejecuta el mismo STA/LTA, firma el cuerpo exacto, publica mediante la
API, verifica que el segundo POST sea duplicado, consume con un consumer group y
confirma una entrada en `stream:seismik:push-test`. La auditoría contiene IDs de
dispositivo, pero nunca el token FCM.

El worker también tiene prueba de mensaje venenoso: tras cinco intentos por
defecto, se mueve a `stream:seismik:dead-letter` y se confirma el mensaje original.

## Bloqueo de infraestructura local

Docker Desktop 4.88.1 se instaló correctamente. El daemon no puede iniciar porque
WSL 2 no está habilitado. Los intentos automatizados devolvieron que DISM requiere
una consola elevada. El Product Owner debe abrir PowerShell como administrador,
ejecutar `wsl --install` y reiniciar Windows. Después Codex ejecutará:

```powershell
docker compose up --build -d
./.venv/Scripts/python.exe tools/run_docker_e2e.py `
  --webhook-secret <secreto-local> `
  --device-key <clave-local>
```

El script crea un dispositivo y una zona efímeros de prueba, nunca activa FCM,
comprueba el payload `TEST` y elimina el dispositivo al terminar.

## Validación actual

- Backend: 55 pruebas aprobadas.
- Ruff: sin hallazgos.
- mypy: sin hallazgos en 34 archivos fuente.
- GCP/facturación: no activados.
- Push APNs/FCM real: no ejecutado.
- Alertas públicas: No-Go por diseño.
