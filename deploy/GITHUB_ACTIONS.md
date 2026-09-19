# Despliegue automático desde GitHub a Cloud Run

El workflow `CI` prueba el commit y, sólo si llega a `main` en verde, despliega
el servicio afectado. No almacena una cuenta de servicio ni una clave privada
en GitHub: GitHub emite un token OIDC de corta duración y Google lo intercambia
por credenciales temporales.

## Configuración única en Google Cloud

Ejecuta esto en Cloud Shell con una cuenta administradora del proyecto. Sustituye
la organización/repositorio sólo si cambia el repositorio público.

```bash
PROJECT_ID=seismik-15bbb
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
POOL=github
PROVIDER=seismik-org
SA=seismik-github-deployer

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com \
  cloudbuild.googleapis.com run.googleapis.com --project "$PROJECT_ID"

gcloud iam service-accounts create "$SA" --project "$PROJECT_ID" \
  --display-name='Seismik GitHub Cloud Run deployer'

for role in roles/run.admin roles/cloudbuild.builds.editor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" --role="$role"
done

gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT_ID" \
  --location=global --display-name='GitHub Actions'

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --project "$PROJECT_ID" --location=global --workload-identity-pool="$POOL" \
  --display-name='seismik-org/seismik' \
  --attribute-mapping='google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref' \
  --attribute-condition="assertion.repository=='seismik-org/seismik' && assertion.ref=='refs/heads/main'" \
  --issuer-uri='https://token.actions.githubusercontent.com'

gcloud iam service-accounts add-iam-policy-binding \
  "$SA@$PROJECT_ID.iam.gserviceaccount.com" --project "$PROJECT_ID" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/seismik-org/seismik"
```

Con sólo esos tres roles `gcloud builds submit` falla antes de construir: «The
user is forbidden from accessing the bucket [seismik-15bbb_cloudbuild]». Para
subir el código, usar la cuota del proyecto y mostrar el registro del build en
GitHub, la cuenta necesita además:

```bash
PROJECT_ID=seismik-15bbb
SA=seismik-github-deployer@$PROJECT_ID.iam.gserviceaccount.com

for role in roles/serviceusage.serviceUsageConsumer roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID"     --member="serviceAccount:$SA" --role="$role" --condition=None
done

# Sólo el bucket donde Cloud Build recibe el código, no todo Cloud Storage.
gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}_cloudbuild"   --member="serviceAccount:$SA" --role=roles/storage.admin
```

`roles/logging.viewer` basta porque `deploy/cloudbuild.*.yaml` envían el
registro a Cloud Logging (`CLOUD_LOGGING_ONLY`); con el bucket de registros por
defecto, `gcloud` exigiría ser Viewer de todo el proyecto.

Cloud Build ya debe tener permiso de escribir en Artifact Registry; se comprueba
con una construcción existente antes de activar esto. El deployer sólo puede
crear builds y actualizar Cloud Run: no recibe `Secret Manager Secret Accessor`
ni permisos de DNS/Cloudflare.

## Variables de GitHub

En **seismik-org/seismik → Settings → Secrets and variables → Actions →
Variables**, crea estas variables de repositorio (no son secretos):

| Variable | Valor |
| --- | --- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/seismik-org` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `seismik-github-deployer@seismik-15bbb.iam.gserviceaccount.com` |

Hasta que ambas existan, las tareas de deploy aparecen como **Skipped** y no
alteran producción.

## Qué se despliega

La API, el dispatcher e integraciones se importan entre sí (el dispatcher decide
la alarma con `api/felt_area.py`; la API usa `eew/official.py`), así que un
cambio en `src/api`, `src/dispatcher`, `src/integrations`, `src/eew`,
`src/crowdsourcing` o `src/reporting` los redespliega a los tres. El detector
sólo depende de `src/eew`. Integraciones fija su comando en Cloud Run
(`python -m dispatcher.integrations`), por eso sirve cualquiera de las dos
imágenes de worker.

Si un deploy falla por permisos, se arreglan los permisos y en GitHub se usa
**Re-run failed jobs** en esa ejecución: no hace falta otro commit. Los cambios de `deploy/cloudflare-edge-router.js` no se
publican automáticamente: requieren un token de Cloudflare con alcance mínimo
y se incorporarán en un workflow separado.
