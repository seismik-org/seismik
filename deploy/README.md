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

## Bootstrap manual de la VM beta

El archivo `bootstrap-beta.sh` inicia solamente Redis, API y dispatcher en modo
`staging`/`dry_run`. Genera secretos aleatorios con permisos `0600`, no los
imprime y conserva un `.env` existente. La API y Redis permanecen enlazados a
`127.0.0.1`; no crea reglas de firewall ni activa FCM/APNs.

Desde la raíz del paquete cargado en la VM:

```bash
bash deploy/bootstrap-beta.sh
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

El detector SeedLink se inicia por separado solo después de validar la salud del
núcleo:

```bash
sudo docker compose --profile detector up --build --detach detector
```
