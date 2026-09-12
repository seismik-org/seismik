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

## Retiro del proxy de la VM

`Dockerfile.web` sirve los archivos estáticos desde Cloud Run. El último paso
es publicar `deploy/cloudflare-edge-router.js` como Worker de zona: enruta los
dominios a la API, Firebase o el sitio estático sin revelar secretos. Tras
validar `seismik.org`, `devs.seismik.org`, `auth.seismik.org` y
`api.seismik.org`, se puede apagar Caddy y finalmente la VM.

## Cerrar la URL directa de la API

Cloud Run publica `seismik-api-331950364408.us-east1.run.app` en Internet. Sin
más, esa URL salta las cabeceras de seguridad y la protección de Cloudflare.
La API la cierra con un secreto compartido (`api/edge_origin.py`):

- el Worker lo añade en `X-Seismik-Origin-Auth` sólo cuando el destino es la
  API (nunca hacia el sitio estático ni hacia Firebase) y borra la que mande un
  cliente;
- el reenviador de Pub/Sub, que llama a la URL directa, envía el mismo;
- sin el secreto configurado la guardia no hace nada, así que el código se
  despliega antes de repartir el valor sin cortar el servicio.

`/health/live` queda exento para las sondas. Los 401 y 403 ya no descartan
eventos en el reenviador: se reintentan, porque indican configuración
desalineada y no un sismo inválido.

**El orden importa.** Si la API exige el secreto antes de que el reenviador lo
tenga, los candidatos quedan reintentándose en Pub/Sub hasta que se corrija
(no se pierden, pero no alertan). Ejecutar en Cloud Shell desde la raíz del
repositorio:

```bash
REGION=us-east1
REPO=us-east1-docker.pkg.dev/seismik-15bbb/seismik

# 1. Crear el secreto (el valor nunca pasa por Git ni por la terminal).
openssl rand -base64 48 | tr -d '\n' | \
  gcloud secrets create seismik-edge-origin --data-file=- --replication-policy=automatic

for service in seismik-api seismik-event-forwarder; do
  sa=$(gcloud run services describe "$service" --region "$REGION" \
    --format='value(spec.template.spec.serviceAccountName)')
  sa=${sa:-331950364408-compute@developer.gserviceaccount.com}
  gcloud secrets add-iam-policy-binding seismik-edge-origin \
    --member="serviceAccount:$sa" --role=roles/secretmanager.secretAccessor
done
```

2. **Worker.** En Cloudflare: Workers y Pages → `seismik` → Configuración →
   Variables y secretos → Agregar → tipo *Secreto*, nombre
   `EDGE_ORIGIN_SECRET`, valor igual al de
   `gcloud secrets versions access latest --secret=seismik-edge-origin`.
   Los secretos del panel se conservan en cada despliegue desde GitHub.

```bash
# 3. Reenviador: imagen nueva con el secreto.
gcloud builds submit --config deploy/cloudbuild.worker.yaml \
  --substitutions=_IMAGE=$REPO/worker:edge-origin,_DOCKERFILE=Dockerfile.dispatcher
gcloud run services update seismik-event-forwarder --region "$REGION" \
  --image "$REPO/worker:edge-origin" \
  --update-secrets=SEISMIK_EDGE_ORIGIN_SECRET=seismik-edge-origin:latest

# 4. API: imagen nueva y, con ella, la guardia activa.
gcloud builds submit --config deploy/cloudbuild.api.yaml \
  --substitutions=_IMAGE=$REPO/api:edge-origin
gcloud run services update seismik-api --region "$REGION" \
  --image "$REPO/api:edge-origin" \
  --update-secrets=SEISMIK_EDGE_ORIGIN_SECRET=seismik-edge-origin:latest

# 5. Comprobar: la URL directa se niega y el dominio público sigue funcionando.
curl -s -o /dev/null -w 'directa %{http_code} (esperado 403)\n' \
  https://seismik-api-331950364408.us-east1.run.app/v1/developer/config
curl -s -o /dev/null -w 'publica %{http_code} (esperado 200)\n' \
  https://api.seismik.org/v1/developer/config
```

`--update-secrets` añade el secreto sin tocar los demás ni las variables de
entorno. Para deshacerlo:

```bash
gcloud run services update seismik-api --region us-east1 \
  --remove-secrets=SEISMIK_EDGE_ORIGIN_SECRET
```
