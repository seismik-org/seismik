#!/usr/bin/env bash
set -euo pipefail
# No secret values in command arguments, files, workflow outputs or logs.
project="${GCP_PROJECT_ID:-seismik-15bbb}"
region="${GCP_REGION:-us-east1}"
secret="seismik-admin-mfa-encryption-key"
# Normal CI only needs Cloud Run permissions. An operator provisions once; do
# not give the GitHub deployer Secret Manager administration rights.
bound_secret="$(gcloud run services describe seismik-api --project "$project" --region "$region" --format=json \
  | python3 -c 'import json,sys; s=json.load(sys.stdin); print(next((e.get("valueFrom",{}).get("secretKeyRef",{}).get("name","") for c in s["spec"]["template"]["spec"]["containers"] for e in c.get("env",[]) if e.get("name")=="SEISMIK_ADMIN_MFA_ENCRYPTION_KEY"),""))')"
if [[ "$bound_secret" == "$secret" ]]; then
  echo "Admin MFA uses the existing Secret Manager binding."
  exit 0
fi
if ! gcloud secrets describe "$secret" --project "$project" >/dev/null 2>&1; then
  python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode(),end="")' \
    | gcloud secrets create "$secret" --project "$project" --replication-policy=automatic --data-file=- --quiet
fi
runtime_sa="$(gcloud run services describe seismik-api --project "$project" --region "$region" --format='value(spec.template.spec.serviceAccountName)')"
if [[ -z "$runtime_sa" ]]; then
  number="$(gcloud projects describe "$project" --format='value(projectNumber)')"
  runtime_sa="${number}-compute@developer.gserviceaccount.com"
fi
gcloud secrets add-iam-policy-binding "$secret" --project "$project" \
  --member="serviceAccount:$runtime_sa" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
gcloud run services update seismik-api --project "$project" --region "$region" \
  --update-secrets="SEISMIK_ADMIN_MFA_ENCRYPTION_KEY=$secret:latest" --quiet
