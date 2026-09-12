# Seismik en Cloud Run

La primera fase migra la **API HTTP** a Cloud Run. Puede escalar a cero y
atiende `api.seismik.org`, las rutas `/v1` de `devs.seismik.org` y el inicio de
sesión de `auth.seismik.org`.

La segunda fase mueve el **dispatcher** de alertas y el consumidor de
**integraciones** a servicios Cloud Run privados con una instancia mínima y CPU
siempre asignada. No deben coexistir con una copia de la VM usando el mismo
consumer group: el corte se hace apagando primero el worker de la VM y luego
habilitando su homólogo de Cloud Run.

## Dependencia obligatoria

Cloud Run no trae Redis. Durante la fase híbrida usa la IP privada del Redis de
la VM mediante Direct VPC Egress; Redis no debe exponerse a Internet. La
migración completa requerirá Memorystore o un Redis gestionado antes de apagar
la VM.

Al mover Redis, copia las claves con `tools/migrate_redis.py` antes y durante
el corte. Usa `DUMP`/`RESTORE`, preserva TTL y nunca imprime valores, claves de
API, tokens ni secretos. No sustituyas datos de producción con un RDB local.

El detector SeedLink **no se mueve todavía**: mantiene una cola de reintento en
el volumen `detector-spool`. El disco de Cloud Run es efímero, así que moverlo
sin sustituir esa cola por Pub/Sub (o una cola durable equivalente) podría
perder candidatos durante un reinicio. Cuando exista esa cola, el detector se
desplegará como worker continuo con salida TCP y un único consumidor activo.

## Secretos

Crear en Secret Manager, una vez y sin poner valores en Git:

```powershell
gcloud secrets create seismik-webhook --data-file=webhook.secret
gcloud secrets create seismik-crowd --data-file=crowd.secret
gcloud secrets create seismik-consumer --data-file=consumer.secret
gcloud secrets create seismik-integration --data-file=integration-webhook.secret
gcloud secrets create seismik-firebase --data-file=firebase-admin.json
```

Concede `roles/secretmanager.secretAccessor` a las cuentas de servicio de los
tres servicios. Después ejecuta:

```powershell
$env:SEISMIK_REDIS_URL = 'redis://IP_PRIVADA_DE_LA_VM:6379/0'
./deploy/cloudrun-deploy.ps1 -Project seismik-15bbb -Region us-east1
```

Con el despliegue activo, el portal `https://devs.seismik.org` puede entregar
claves gratuitas después del inicio de sesión Firebase/Google. La clave se
presenta una sola vez y se guarda como hash en Redis; nunca la incluyas en Git.

El API se limita inicialmente a 0–2 instancias. Antes de sustituir Redis y los
workers, valida salud, registro de dispositivos, OAuth y entrega de alertas.
Los workers continuos usan facturación por instancia y una instancia mínima;
no escalan a cero y no son gratuitos.
