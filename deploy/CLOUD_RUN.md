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
   Los secretos del panel se conservan en cada despliegue desde GitHub; las
   variables de **texto** no: el siguiente push las borra, el Worker deja de
   enviar la cabecera y todo `api.seismik.org` y `auth.seismik.org` responde
   403 «Origin not allowed». Al editarlo, comprobar que el tipo siga en
   *Secret*.

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

## Rotar el secreto de origen

**Nunca con `:latest`.** Cloud Run lee el secreto al arrancar cada instancia.
Con `seismik-edge-origin:latest`, crear una versión nueva no cambia nada en el
momento, pero la siguiente instancia que arranque (la API escala a cero) toma
el valor nuevo mientras el Worker sigue enviando el anterior: todo lo que llega
por Cloudflare recibe 403. Por eso los servicios apuntan a un número de versión
y la rotación mueve las tres piezas a la vez:

```bash
REGION=us-east1

# 1. Versión nueva sin salto de línea. Anotar el número que imprime (N).
openssl rand -base64 48 | tr -d '\n' | \
  gcloud secrets versions add seismik-edge-origin --data-file=-
```

2. **Preparar el Worker sin guardar.** Cloudflare → `seismik` → Settings →
   `EDGE_ORIGIN_SECRET` → editar y pegar el valor de la versión N (Secret
   Manager → `seismik-edge-origin` → versión N → *Ver valor del secreto*).
   El tipo debe quedar en *Secret*, no *Text*: una variable de texto funciona
   hasta el siguiente despliegue desde GitHub, que la borra. Dejar el
   formulario abierto.

```bash
# 3. API con la versión N. En cuanto termine, guardar/desplegar el Worker:
#    entre ambos pasos api.seismik.org responde 403.
N=2
gcloud run services update seismik-api --region "$REGION" \
  --update-secrets=SEISMIK_EDGE_ORIGIN_SECRET=seismik-edge-origin:$N

# 4. Reenviador. Mientras tanto sus eventos se reintentan; no se pierden.
gcloud run services update seismik-event-forwarder --region "$REGION" \
  --update-secrets=SEISMIK_EDGE_ORIGIN_SECRET=seismik-edge-origin:$N

# 5. Comprobar como en el paso 5 de arriba.
```

La versión anterior se puede **inhabilitar** (no destruir) un día después:
si algo quedó apuntando a ella, se vuelve a habilitar al instante.

## Publicador de X

Corre dentro de `seismik-integrations` (`dispatcher/integrations.py`), no como
servicio propio. Lee Redis en segundo plano y nunca recibe peticiones: con
facturación basada en solicitudes Cloud Run no le asigna CPU, y un servicio
propio con `--no-cpu-throttling` costaría unos 40 USD/mes más. Integraciones ya
tiene la CPU siempre asignada. Si el publicador falla, se registra y se reinicia
sin detener los webhooks.

Publica los sismos nuevos de las agencias de `official_sources.json`: consulta
sus catálogos cada 2 minutos (`SEISMIK_X_PUBLISHER_POLL_SECONDS`) y publica una
vez cada sismo con origen en la última hora y magnitud desde
`SEISMIK_X_PUBLISHER_MINIMUM_MAGNITUDE`. Un sismo que reportan varias agencias
sale una sola vez, con el reporte local; dentro de los países de una agencia
local, el USGS espera 15 minutos a que ésta lo publique. Las detecciones
propias por SeedLink no se publican (`SEISMIK_X_PUBLISHER_SOURCE=official_catalogs`;
`seismik_detections` usaría el stream de integraciones).

Por defecto no publica (`SEISMIK_X_PUBLISHER_ENABLED=false`,
`SEISMIK_X_PUBLISHER_DRY_RUN=true`): sólo audita en `stream:seismik:x-audit`.
Conviene desplegar primero así unos minutos: los sismos de la última hora quedan
marcados y al activar la publicación sólo salen los nuevos.

```bash
REGION=us-east1
REPO=us-east1-docker.pkg.dev/seismik-15bbb/seismik

# 1. Acceso de la cuenta de servicio de integraciones a las credenciales de X.
sa=$(gcloud run services describe seismik-integrations --region "$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')
sa=${sa:-331950364408-compute@developer.gserviceaccount.com}
for secret in seismik-x-consumer-key seismik-x-consumer-secret \
  seismik-x-access-token seismik-x-access-token-secret; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:$sa" --role=roles/secretmanager.secretAccessor
done

# 2. Imagen nueva de integraciones con las credenciales.
gcloud builds submit --config deploy/cloudbuild.worker.yaml \
  --substitutions=_IMAGE=$REPO/worker:x-embedded,_DOCKERFILE=Dockerfile.dispatcher
gcloud run services update seismik-integrations --region "$REGION" \
  --image "$REPO/worker:x-embedded" \
  --update-secrets=SEISMIK_X_CONSUMER_KEY=seismik-x-consumer-key:latest,SEISMIK_X_CONSUMER_SECRET=seismik-x-consumer-secret:latest,SEISMIK_X_ACCESS_TOKEN=seismik-x-access-token:latest,SEISMIK_X_ACCESS_TOKEN_SECRET=seismik-x-access-token-secret:latest

# 3. Publicar de verdad, cuando se decida.
gcloud run services update seismik-integrations --region "$REGION" \
  --update-env-vars=SEISMIK_X_PUBLISHER_ENABLED=true,SEISMIK_X_PUBLISHER_DRY_RUN=false
```

Mientras convivan con un servicio `seismik-x-publisher` anterior, ambos leen el
mismo grupo de Redis: cada mensaje llega a uno solo y la marca de «publicado»
evita duplicados. Ese servicio se puede retirar en cuanto integraciones arranque
bien; `Dockerfile.x-publisher` queda por si algún día conviene separarlo (por
ejemplo, como worker pool).

## Alarma por perímetro de sacudida

A quién le llega cada aviso lo decide la intensidad (Mercalli) que se espera en
la ubicación de cada teléfono (`api/felt_area.py`, `dispatcher/policy.py`), no
la magnitud mínima ni el radio que eligió la persona:

- Sacudida fuerte (VI o más): alarma siempre, aunque haya apagado los avisos.
  Un reporte oficial de un sismo con más de 30 minutos
  (`SEISMIK_OFFICIAL_ALARM_MAX_AGE_MINUTES`) llega como aviso.
- Alerta temprana: alarma desde sacudida ligera (IV) para quien la tiene activa.
- Reporte oficial: aviso desde intensidad III para quien los recibe.
- Sin magnitud o sin epicentro no hay perímetro: se usan la magnitud mínima y
  el radio de siempre.
- El mismo sismo reportado por otra agencia no vuelve a avisar, salvo que su
  magnitud suba 0,5 o más.

Hasta ahora el dispatcher sólo recibía reportes oficiales de sismos que SeedLink
había detectado. `seismik-integrations` ahora puede consultar cada minuto los
catálogos de `official_sources.json` (`integrations/catalog_alerts.py`) y dejar
en `stream:seismik:official` cada sismo que alguien pudo sentir. Está apagado
por defecto (`SEISMIK_CATALOG_ALERTS_ENABLED=false`). Los webhooks de
organizaciones no reciben esos sismos. Las alertas respetan `SEISMIK_PUSH_MODE`
del dispatcher: en `testers` sólo llegan a los teléfonos de prueba.

```bash
REGION=us-east1
REPO=us-east1-docker.pkg.dev/seismik-15bbb/seismik

# 1. Imágenes nuevas: el dispatcher decide la alarma, la API la aplica a la
#    bitácora de alertas perdidas e integraciones consulta los catálogos.
gcloud builds submit --config deploy/cloudbuild.worker.yaml \
  --substitutions=_IMAGE=$REPO/worker:felt-perimeter,_DOCKERFILE=Dockerfile.dispatcher
gcloud builds submit --config deploy/cloudbuild.api.yaml \
  --substitutions=_IMAGE=$REPO/api:felt-perimeter
for service in seismik-dispatcher seismik-integrations; do
  gcloud run services update "$service" --region "$REGION" \
    --image "$REPO/worker:felt-perimeter"
done
gcloud run services update seismik-api --region "$REGION" \
  --image "$REPO/api:felt-perimeter"

# 2. Alertas de los catálogos oficiales, cuando se decida.
gcloud run services update seismik-integrations --region "$REGION" \
  --update-env-vars=SEISMIK_CATALOG_ALERTS_ENABLED=true
```

## Iniciar sesión con Apple

`auth.seismik.org` ofrece Apple junto a Google y GitHub (`api/oauth.py`). La
página de acceso y la app de iPhone usan el mismo flujo web; el botón sólo
aparece cuando la API tiene los cuatro valores. Apple no da un secreto fijo: la
API firma uno de cinco minutos con la clave `.p8` en cada inicio de sesión.
Las cuentas de Apple son nuevas (`apple:<id>`), aunque el correo coincida con
una cuenta de Google, y pueden usar el correo de reenvío privado de Apple.

En Apple Developer, una vez:

1. **Identifiers → App IDs → `com.seismik.app`**: activar *Sign In with Apple*.
2. **Identifiers → + → Services IDs**: identificador `org.seismik.auth`.
   Activar *Sign In with Apple* → *Configure*: App ID principal
   `com.seismik.app`, dominio `auth.seismik.org` y Return URL
   `https://auth.seismik.org/v1/oauth/apple/callback`.
3. **Keys → +**: activar *Sign In with Apple* con `com.seismik.app` y descargar
   `AuthKey_<KEY_ID>.p8` (Apple la entrega una sola vez). El Team ID está en
   *Membership*.

En Cloud Shell, tras subir el `.p8` con el menú ⋮ → Subir:

```bash
REGION=us-east1
REPO=us-east1-docker.pkg.dev/seismik-15bbb/seismik

# 1. La clave como secreto (queda en la versión 1) y acceso para la API.
gcloud secrets create seismik-apple-private-key --replication-policy=automatic \
  --data-file=AuthKey_KEY_ID.p8
sa=$(gcloud run services describe seismik-api --region "$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')
sa=${sa:-331950364408-compute@developer.gserviceaccount.com}
gcloud secrets add-iam-policy-binding seismik-apple-private-key \
  --member="serviceAccount:$sa" --role=roles/secretmanager.secretAccessor
rm AuthKey_KEY_ID.p8

# 2. API con Apple. Versión fija del secreto: `:latest` se resuelve al arrancar.
gcloud builds submit --config deploy/cloudbuild.api.yaml \
  --substitutions=_IMAGE=$REPO/api:apple-sign-in
gcloud run services update seismik-api --region "$REGION" \
  --image "$REPO/api:apple-sign-in" \
  --update-env-vars=SEISMIK_OAUTH_APPLE_CLIENT_ID=org.seismik.auth,SEISMIK_OAUTH_APPLE_TEAM_ID=TEAM_ID,SEISMIK_OAUTH_APPLE_KEY_ID=KEY_ID \
  --update-secrets=SEISMIK_OAUTH_APPLE_PRIVATE_KEY=seismik-apple-private-key:1

# 3. Página de acceso con el botón de Apple.
gcloud builds submit --config deploy/cloudbuild.worker.yaml \
  --substitutions=_IMAGE=$REPO/web:apple-sign-in,_DOCKERFILE=Dockerfile.web
gcloud run services update seismik-web --region "$REGION" \
  --image "$REPO/web:apple-sign-in"

# 4. Debe mostrar "apple": {"enabled": true}.
curl -s https://auth.seismik.org/v1/oauth/providers
```

## App Check en iPhone

La app de iPhone pide a Firebase App Check un token respaldado por DeviceCheck
antes de registrarse. Si Firebase no lo entrega (DeviceCheck sin configurar en
la consola de Firebase), el registro envía un marcador no verificado, como el
cliente Android en beta, y el iPhone recibe alertas y usa Familia. En cuanto la
API verifique App Check (`SEISMIK_INTEGRITY_VERIFICATION_ENABLED=true`), ese
marcador se rechaza: antes hay que subir la clave de DeviceCheck en Firebase →
App Check → Apps → iOS.
