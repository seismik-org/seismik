# Seismik en Cloud Run

La primera fase migra la **API HTTP** a Cloud Run. Puede escalar a cero y
atiende `api.seismik.org`, las rutas `/v1` de `devs.seismik.org` y el inicio de
sesión de `auth.seismik.org`. El detector SeedLink, dispatcher e integrations
permanecen en la VM: son consumidores continuos y ejecutar una segunda copia
en Cloud Run duplicaría entregas de alertas.

## Dependencia obligatoria

Cloud Run no trae Redis. Durante la fase híbrida usa la IP privada del Redis de
la VM mediante Direct VPC Egress; Redis no debe exponerse a Internet. La
migración completa requerirá Memorystore o un Redis gestionado antes de apagar
la VM. El detector SeedLink necesita salida TCP persistente y no se mueve en
esta fase.

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
workers, valida salud, registro de dispositivos, OAuth y entrega de alertas;
una instancia continua de detector o dispatcher no es gratuita.
