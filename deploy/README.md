# Preparación de despliegue — no ejecuta recursos

Este directorio registra límites para el futuro ambiente beta. Su presencia no
autoriza activar GCP, vincular facturación ni aplicar infraestructura.

## Gate previo a cualquier despliegue

1. Sprint 3 local completo y aceptado.
2. Presupuesto mensual y alerta de facturación aprobados por el Product Owner.
3. Proyecto GCP separado de producción y credenciales sin incluir en Git.
4. `SEISMIK_PUSH_ENABLED=false` y `SEISMIK_PUSH_MODE=dry_run` inicialmente.
5. Redis con AOF, backup probado y acceso solo desde red privada.
6. API con TLS, límite de cuerpo 64 KiB y secretos en Secret Manager.

## Límites iniciales propuestos para beta

| Control | Valor inicial |
|---|---:|
| Cuerpo máximo de evento | 65.536 bytes |
| Retención aproximada por Stream | 100.000 entradas |
| Lote de consumidor | 10 mensajes |
| Intentos antes de DLQ | 5 |
| Cooldown crítico por zona | 60 s |
| Concurrencia FCM | 20 lotes de máximo 500 |
| Concurrencia APNs | 100 solicitudes |
| Push | Deshabilitado / `dry_run` |

## Arquitectura beta propuesta

Primero se validará Docker Compose en una sola máquina de pruebas. Antes de
alertas públicas se exigirá Redis administrado o redundante, dos instancias del
detector en regiones independientes, balanceo del API, observabilidad y un plan
de continuidad. Kubernetes y TPU no son requisitos del MVP.

La futura IaC se añadirá después de elegir proyecto, región, dominio, presupuesto
y modelo Redis. No se incluye Terraform que pueda crear recursos facturables sin
esas decisiones, evitando un `apply` accidental.
