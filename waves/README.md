# Seismik Waves — historical access pilot

Portal: https://waves.seismik.org/ · Explorer: https://waves.seismik.org/explore

This isolated pilot serves 560 historical MiniSEED recordings from the verified 2026-10-10
Cloud Storage import: a readable catalogue, a waveform explorer and, once enabled, the complete
original MiniSEED file. It does **not** publish live events, send push notifications, calculate
magnitude remotely or alter the scientific validation of the source data. All original files
remain private in `seismik-15bbb-scientific-archive`; the remaining 41 import files are
calibration and station metadata, not waveforms.

## Access

Same single sign-on as `admin.seismik.org`, without Firebase in this portal: «Entrar» goes to
`auth.seismik.org/id`, the person signs in there (Google, GitHub, Apple or email) and Seismik
returns them to Waves with the `seismik_session` cookie (HttpOnly, `.seismik.org`). The Worker
forwards **only that cookie** to the backend; the backend asks `api.seismik.org/v1/oauth/session`
who the session belongs to and only then compares the email with `WAVES_PILOT_EMAILS`
(semicolon-separated allowlist, empty = nobody; currently one address). The browser never decides
authorization, and a signed-in account is not automatically approved.

The return to Waves needs the small change in `src/api/oauth.py` (`seismik_after_login=waves`
marker → `waves_portal_url`). Without it sign-in still works but ends on `devs.seismik.org`.
«Cerrar sesión» ends the shared Seismik session in every portal.

## Pages and API

- `/` portal · `/explore?id=…` waveform explorer (`/explorar` redirects here) · `/login` hand-off to auth.
- `GET /health/ready`, `GET /v1/waves/summary` — public aggregates (counts per group, no names).
- `GET /v1/waves/session` — access state.
- `GET /v1/waves/catalog` — approved only: `q`, `kind`, `group`, `minimum_magnitude`, `sort`, `offset`, `limit`.
- `GET /v1/waves/records/{id}` — metadata and SHA-256.
- `GET /v1/waves/records/{id}/preview` — min/max envelope (600 intervals per channel) to draw waveforms.
  It is a reduction, not the recording, and cannot reconstruct it.
- `GET /v1/waves/records/{id}/download` — the **original, complete MiniSEED file**. Off unless
  `WAVES_DOWNLOADS=on`. The backend reads it from the private archive, checks size and SHA-256
  against the catalogue **before** sending a byte (502 if they differ), limits 20 downloads per
  minute per person and logs `id` and a hash of the email (never the address).
- `POST /v1/waves/logout` — only from `https://waves.seismik.org`.

Private responses are never cached. There is no bucket listing or path-based download.

## Hosting

`seismik-waves-edge` (Cloudflare Worker, route `waves.seismik.org/*`) serves `static/` with Workers
Static Assets and forwards `/v1/*` and `/health/*` to the Cloud Run service `seismik-waves`
(`us-east1`, project `seismik-15bbb`). The catalogue and previews exist only in Cloud Run; nothing
private is in the Worker bundle. Firebase Hosting for Waves was retired on 2026-10-11 (project
`seismik-15bbb` and its shared authentication are untouched). The Worker and `waves/app.py` publish
the same Content-Security-Policy (a test enforces it): first-party scripts only, no frames.

Cloud Run: 256 MiB, request-based CPU, minimum zero instances, maximum two, timeout 30 s.

## Rebuild

```powershell
& ./work/seismik-public-clean/waves/prepare.ps1          # catalog.json from the verified manifest
& ./work/python-validation/.venv/Scripts/python.exe ./work/seismik-public-clean/waves/build-previews.py   # previews/ and catalog-view.json (needs obspy; verifies every SHA-256)
& ./work/python-validation/.venv/Scripts/python.exe -m pytest ./work/seismik-public-clean/waves/tests -q
node ./work/seismik-public-clean/waves/tests/edge.test.cjs
& ./work/tools/gcloud-581/google-cloud-sdk/bin/gcloud.cmd builds submit ./work/seismik-public-clean/waves --project=seismik-15bbb --region=us-east1 --tag=us-east1-docker.pkg.dev/seismik-15bbb/seismik/waves:CHOOSE_NEW_TAG
```

Deploy the resulting **image digest** with `--no-traffic --tag=candidate`, test the candidate URL,
then move traffic. Deploy the Worker from `waves/edge` with Wrangler. Never deploy Waves changes to
the detector, API or dispatcher; main Seismik CD does not deploy Waves.

## Downloads and the archive

Downloads need the runtime service account (`seismik-waves-runtime`) to read the archive. Grant it
read-only access to the import prefix only (`roles/storage.objectViewer` with the condition
`resource.name.startsWith("projects/_/buckets/seismik-15bbb-scientific-archive/objects/imports/local-2026-10-10/data/")`),
then set `WAVES_DOWNLOADS=on` on the service. Each source keeps its own terms and attribution.
