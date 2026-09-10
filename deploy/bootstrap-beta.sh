#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required; install it with: sudo apt-get install -y openssl" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  umask 077
  webhook_secret="$(openssl rand -hex 32)"
  consumer_key="$(openssl rand -hex 32)"
  crowd_secret="$(openssl rand -hex 32)"
  integration_secret="$(openssl rand -hex 32)"
  cat >.env <<EOF
SEISMIK_ENVIRONMENT=staging
SEISMIK_WEBHOOK_HMAC_SECRET=${webhook_secret}
SEISMIK_CONSUMER_API_KEY=${consumer_key}
SEISMIK_CROWD_MASTER_SECRET=${crowd_secret}
SEISMIK_INTEGRATION_WEBHOOK_MASTER_SECRET=${integration_secret}
SEISMIK_PUSH_ENABLED=false
SEISMIK_PUSH_MODE=dry_run
SEISMIK_PUSH_TEST_DEVICE_IDS=[]
SEISMIK_INTEGRITY_VERIFICATION_ENABLED=false
EOF
  chmod 600 .env
  unset webhook_secret consumer_key crowd_secret integration_secret
  echo "Created a private .env with random beta secrets."
else
  echo "Keeping the existing .env file."
fi

sudo docker compose config --quiet
sudo docker compose up --build --detach redis api dispatcher integrations

for _attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8000/health/ready >/dev/null; then
    echo "Seismik beta core is ready on the VM loopback interface."
    sudo docker compose ps
    exit 0
  fi
  sleep 2
done

echo "The API did not become ready; showing recent logs." >&2
sudo docker compose logs --no-color --tail 100 api redis dispatcher integrations >&2
exit 1
