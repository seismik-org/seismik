param(
  [string]$Project = $(if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { "seismik-15bbb" }),
  [string]$Region = "us-east1",
  [string]$RedisUrl = $env:SEISMIK_REDIS_URL
)

$ErrorActionPreference = "Stop"
$gcloud = "gcloud"
if (-not $RedisUrl) {
  throw "SEISMIK_REDIS_URL es obligatorio. Cloud Run no incluye Redis; usa Memorystore/Redis gestionado y no una URL localhost."
}
foreach ($secret in @("seismik-webhook", "seismik-crowd", "seismik-consumer", "seismik-integration", "seismik-firebase")) {
  & $gcloud secrets describe $secret --project $Project *> $null
  if ($LASTEXITCODE -ne 0) { throw "Falta el secreto $secret en Secret Manager." }
}

& $gcloud config set project $Project | Out-Null
& $gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

function Deploy-Service([string]$name, [string]$dockerfile, [string]$min, [string]$max) {
  & $gcloud run deploy $name `
    --source . `
    --dockerfile $dockerfile `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --min-instances $min `
    --max-instances $max `
    --cpu 1 `
    --memory 512Mi `
    --set-env-vars "SEISMIK_ENVIRONMENT=production,SEISMIK_REDIS_URL=$RedisUrl,SEISMIK_INTEGRITY_VERIFICATION_ENABLED=true,SEISMIK_PUSH_ENABLED=true,SEISMIK_PUSH_MODE=production,SEISMIK_FIREBASE_CREDENTIALS_PATH=/secrets/firebase-admin.json,PORT=8080" `
    --set-secrets "SEISMIK_WEBHOOK_HMAC_SECRET=seismik-webhook:latest,SEISMIK_CROWD_MASTER_SECRET=seismik-crowd:latest,SEISMIK_CONSUMER_API_KEY=seismik-consumer:latest,SEISMIK_INTEGRATION_WEBHOOK_MASTER_SECRET=seismik-integration:latest" `
    --update-secrets "/secrets/firebase-admin.json=seismik-firebase:latest"
}

Deploy-Service "seismik-api" "Dockerfile.api" "0" "2"
Deploy-Service "seismik-dispatcher" "Dockerfile.dispatcher" "1" "1"
Deploy-Service "seismik-integrations" "Dockerfile.integrations" "1" "1"
Deploy-Service "seismik-detector" "Dockerfile" "1" "1"

Write-Host "Cloud Run desplegado. Configura el CNAME devs/api con las URLs que devuelve gcloud run services describe."
