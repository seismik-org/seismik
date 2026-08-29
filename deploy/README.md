# Preparación y operación del despliegue beta

Este directorio registra límites y procedimientos del ambiente beta. Ningún
script crea proyectos GCP, vincula facturación ni modifica reglas de firewall;
esas acciones requieren autorización explícita del Product Owner.

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

## Publicación HTTPS detrás de Cloudflare

La API permanece enlazada a `127.0.0.1:8000`. El único punto de entrada
público es Caddy en 80/443, definido en `docker-compose.public.yml`:

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.firebase.yml \
  -f docker-compose.public.yml \
  --profile detector up -d
```

Si el paquete incluye `docker-compose.global.yml`, puede añadirse como overlay
opcional entre los dos archivos anteriores para ejecutar el catálogo global de
proveedores. La beta actual usa el detector definido en `docker-compose.yml`.

La credencial Firebase se instala únicamente como
`secrets/firebase-admin.json`, con permisos `0600`, y se monta de solo lectura.
El archivo está excluido de Git. Tener la credencial montada no activa envíos:
la beta conserva `SEISMIK_PUSH_ENABLED=false` y `SEISMIK_PUSH_MODE=dry_run`
hasta registrar explícitamente los dispositivos de prueba.

Requisitos de red para producción:

- `api.seismik.org`, `seismik.org` y `www.seismik.org` deben estar bajo proxy
  de Cloudflare.
- La VM debe aceptar TCP 80/443 exclusivamente desde los rangos IP oficiales
  de Cloudflare y mantener 6379/8000 sin exposición pública.
- Cloudflare SSL/TLS debe quedar en `Full (strict)` después de que Caddy emita
  los certificados del origen.
- El registro de firewall se mantiene desactivado en la beta para evitar
  costos inesperados de Cloud Logging.

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

## Actualizar una beta existente

Los paquetes no incluyen `.env`, credenciales ni datos de Redis. Por tanto, una
actualización puede extraerse sobre `/home/todozhop/seismik` sin reemplazar los
secretos ni el volumen persistente:

```bash
cd /home/todozhop/seismik
unzip -oq ~/seismik-beta-0.4.1.zip -d .
docker compose --profile detector up --build --detach detector
docker compose logs --tail 100 --follow detector
```

La versión `0.4.1` corrige la creación del cliente SeedLink para establecer el
timeout de conexión antes de abrir el socket, requerido por ObsPy 1.4.x.
