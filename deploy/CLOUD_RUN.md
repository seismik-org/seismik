# Seismik en Cloud Run

El despliegue deja de depender de la VM para API, dispatcher y detector. API
escala a cero; dispatcher y detector mantienen una instancia porque consumen
Redis/SeedLink continuamente. Cada worker expone `/healthz` para cumplir el
contrato de Cloud Run.

## Dependencia obligatoria

Cloud Run no trae Redis. Antes de ejecutar `cloudrun-deploy.ps1` hay que crear
Redis gestionado (Memorystore con conector VPC, o un Redis administrado
compatible) y exportar `SEISMIK_REDIS_URL`. Mantener la VM solo como Redis no es
una migración completa. La instancia detectora de Cloud Run también debe tener
salida TCP a los servidores SeedLink.

## Secretos

Crear en Secret Manager, una vez y sin poner valores en Git:

```powershell
gcloud secrets create seismik-webhook --data-file=webhook.secret
gcloud secrets create seismik-device --data-file=device.secret
gcloud secrets create seismik-crowd --data-file=crowd.secret
gcloud secrets create seismik-consumer --data-file=consumer.secret
gcloud secrets create seismik-firebase --data-file=firebase-admin.json
```

Concede `roles/secretmanager.secretAccessor` a las cuentas de servicio de los
tres servicios. Después ejecuta:

```powershell
$env:SEISMIK_REDIS_URL = 'rediss://usuario:clave@host:6379/0'
./deploy/cloudrun-deploy.ps1 -Project seismik-15bbb -Region us-east1
```

El script configura límites bajos (API 0–2 instancias y workers 1 instancia)
para evitar consumo accidental. Revisa costos antes de subir el detector: una
instancia siempre activa no es gratuita.
