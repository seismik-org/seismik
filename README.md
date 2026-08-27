# Seismik

**Estado del producto:** Prototipo Alfa 0.1. El código actual es una base de
ingeniería y todavía no es un MVP operativo ni un sistema certificado. El objetivo
de los primeros ocho sprints es entregar el **MVP Experimental 1.0 para Colombia**,
en Android, modo sombra y con pruebas controladas.

**Sprint 1 cerrado técnicamente (2026-08-24):** entorno Python 3.12.10,
catálogo colombiano fechado, reconexión/gaps auditables y replay determinista
de tres sismos históricos más una ventana ambiente. Los resultados muestran
falsos candidatos en ruido con los parámetros actuales; por eso Seismik sigue en
modo sombra y la calibración científica pertenece al Sprint 2.

**Sprint 2 cerrado técnicamente (2026-08-24):** 15 estaciones CM configuradas,
perfiles DSP por red, geometría y lag exigidos en la coincidencia, matriz de 36
configuraciones y contrato de actualización SGC probado. La configuración sombra
detectó los tres casos históricos y no produjo candidatos en cinco minutos de
ruido ambiente, pero su latencia media fue 56,552 s. El corpus es pequeño y no
incluye una validación sismológica independiente: sigue siendo **No-Go público**.

**Sprint 3 en curso (2026-08-26):** contratos OpenAPI estrictos, ingesta HMAC
idempotente, Redis Streams/DLQ y pipeline replay → API → dispatcher validados en
memoria. El modo `dry_run` guarda un payload marcado `TEST` sin tokens ni envío
externo. Docker Desktop quedó instalado; falta habilitar WSL 2 como administrador,
reiniciar Windows y repetir la misma prueba con Compose para cerrar el Sprint.

## Gobierno, Scrum y control de avance

La fuente compartida y verificable de planificación se encuentra en
[`docs/project-management/`](docs/project-management/README.md). Contiene fuentes
Markdown revisables en Git y copias formales en Word:

- Documento maestro del proyecto, alcance y hoja de ruta.
- Plan Scrum de ocho sprints, responsables, entregables y checkpoints.
- Control de avance, riesgos, decisiones, impedimentos y checklist Go/No-Go.

Las fotografías, los videos, iOS, la expansión mundial, las alertas públicas
automáticas y las integraciones IoT quedan fuera del MVP inicial. Todo simulacro
debe permanecer restringido a testers autorizados y marcado visiblemente como
`TEST` o `SIMULACRO`.

Seismik es una plataforma modular de alerta sísmica temprana: recibe formas de
onda SeedLink, detecta candidatos mediante STA/LTA y coincidencia multiestación,
incorpora señales voluntarias de acelerómetros móviles y distribuye alertas por
APNs/FCM. Después de la detección enlaza reportes oficiales de servicios
geológicos; estos reportes confirman y refinan, pero no bloquean la alerta inicial.

> **Uso responsable:** este repositorio es una base de ingeniería, no un sistema
> certificado de protección civil. Una alerta pública exige validación
> sismológica, observabilidad 24/7, redundancia multirregional, simulacros,
> acuerdos con operadores y revisión legal en cada jurisdicción.

## Arquitectura consolidada

```text
SeedLink/FDSN ──> detector ObsPy ──HMAC──> FastAPI ──> Redis Streams
                                                │             │
Flutter/App Check ──pings HMAC──> H3 res. 7 + Lua             │
                                                              v
                                             consumer groups / DLQ
                                                              │
                                       APNs HTTP/2 + FCM multicast
                                                              │
                                                    iOS / Android
```

- `src/eew/`: adquisición SeedLink, DSP, STA/LTA, coincidencia y correlación
  posterior con fuentes oficiales.
- `src/api/`: webhooks firmados, registro atestado, catálogo público y gestión de
  dispositivos.
- `src/crowdsourcing/`: pings firmados y quorum espacio-temporal H3.
- `src/dispatcher/`: consumidor durable, geocercas, cooldown y push masivo.
- `mobile_app/`: aplicación Flutter por capas, App Check, DSP local, mapas y UI.

## H3 y concurrencia

Cada ping se asigna con `latlng_to_cell(..., 7)`. El script Lua inserta el
`device_id` en un sorted set de la celda primaria, poda una ventana de 2.5 s y
calcula la unión única de esa celda y `grid_disk(H, 1)`. Con diez dispositivos
distintos crea un `crowdsourced_earthquake_candidate` y bloquea las siete celdas
durante el cooldown. Así una ráfaga del mismo teléfono no aumenta el quorum y dos
celdas adyacentes no publican el mismo cluster.

La transacción multi-key es adecuada para Redis standalone o Sentinel. Redis
Cluster no permite un Lua atómico sobre distintos hash slots; para Cluster se
debe introducir un agregador propietario de partición o ejecutar este estado en
una instancia dedicada no-cluster.

Streams:

- `stream:seismik:candidates`
- `stream:seismik:official`
- `stream:seismik:dead-letter`

## Seguridad

Los webhooks y pings firman exactamente `timestamp + "." + raw_body` con
HMAC-SHA256:

- `X-Seismik-Timestamp`
- `X-Seismik-Signature`
- `X-Seismik-Device-Key` solo para bootstrap de registro

El registro exige `app_attest_token` en iOS o `play_integrity_token` en Android.
Esos campos transportan un **Firebase App Check token** corto respaldado por App
Attest/DeviceCheck o Play Integrity; el servidor lo verifica con Firebase Admin.
La clave bootstrap incluida en una app es extraíble y no sustituye App Check,
rate limiting perimetral ni rotación de secretos.

En producción, `SEISMIK_INTEGRITY_VERIFICATION_ENABLED=true` es obligatorio por
validación de configuración. Restrinja también los Firebase App IDs permitidos.

## Backend local

Requiere Docker Compose o Python 3.12.

```bash
cp .env.example .env
docker compose up --build
```

Servicios:

- API/OpenAPI: `http://localhost:8000/docs`
- salud: `/health/live` y `/health/ready`
- detector opcional: `docker compose --profile detector up --build`

Ejecución Python:

```bash
python --version  # debe indicar 3.12.10
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-test.txt
.venv/Scripts/pip install -e .
.venv/Scripts/seismik-api
.venv/Scripts/seismik-dispatcher
.venv/Scripts/seismik-detector --config config.json
```

Pruebas y análisis:

```bash
pytest
ruff check src tests
mypy src
```

Contrato e integración del Sprint 3:

- `docs/api/openapi-v1.json`: contrato OpenAPI exportado y versionado.
- `docs/architecture/ADR-0001-redis-streams-mvp.md`: decisión Redis vs. Pub/Sub.
- `stream:seismik:push-test`: auditoría de simulacros sin tokens APNs/FCM.
- `tools/run_docker_e2e.py`: replay histórico contra API, Redis y dispatcher reales.

Push permanece en `SEISMIK_PUSH_MODE=dry_run`. Para una prueba FCM real se exige
`push_mode=testers`, `push_enabled=true` y una allowlist explícita de dispositivos.
El modo `production` se rechaza si el ambiente no está declarado como producción.

Evidencia y replay del Sprint 1:

- `data/stations/colombia-stations-2026-08-24.json`: metadatos, presencia de
  datos recientes y probes TCP.
- `data/stations/seedlink-probe-2026-08-24.json`: paquete real
  `CM.ARGC.00.HHZ`, con lag puntual observado; no es una garantía de uptime.
- `data/replay/manifest.json`: procedencia y SHA-256 de cuatro fixtures.
- `data/replay/results/`: salida canónica con reloj derivado de MiniSEED.

```powershell
.\.venv\Scripts\seismik-replay `
  --config config.json `
  --manifest data\replay\manifest.json `
  --case co-2023-08-17-m6.1 `
  --output work\replay.json
```

El verificador FDSN separa la antigüedad deliberada de la consulta de archivo
de la latencia SeedLink. No debe usarse la primera como si fuera latencia EEW.

Calibración sombra del Sprint 2:

- `data/calibration/sprint2-grid-expanded.json`: 36 perfiles evaluados.
- `data/calibration/sprint2-two-station-tradeoff.json`: evidencia de por qué no
  se adoptó el quorum más rápido de dos estaciones.
- `data/replay/results-sprint2/`: resultados canónicos con tres estaciones.
- `data/calibration/sgc-association.json`: alcance real del feed rápido quincenal.
- `docs/project-management/PAQUETE_REVISION_SISMOLOGICA_v0.1.md`: paquete que
  debe revisar una universidad o profesional de sismología.

## Push a gran escala

- FCM usa `send_each_for_multicast_async()` en grupos exactos de hasta 500
  tokens y varios lotes concurrentes, limitados por `SEISMIK_FCM_CONCURRENCY`.
- APNs reutiliza un cliente HTTP/2 `aioapns`; un semáforo limita a 100 solicitudes
  simultáneas por worker.
- `BadDeviceToken`, `Unregistered` y errores equivalentes eliminan el dispositivo
  inmediatamente de Redis.
- Para millones de destinatarios deben desplegarse múltiples workers con nombres
  de consumidor únicos y particionar el fan-out; el batching evita explosión de
  conexiones, pero una sola instancia no constituye capacidad multirregional.

## Aplicación Flutter

Se requiere Flutter 3.41+ / Dart 3.11+. El proyecto incluye el host completo de
Android y iOS, wrapper Gradle, proyecto Xcode, manifiestos, sonidos y entitlements:

```bash
cd mobile_app
flutter pub get
```

En una estación Windows nueva, instala JDK 17 y Android SDK, acepta personalmente
la licencia y completa los paquetes de compilación:

```powershell
flutter doctor --android-licenses
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"
flutter doctor -v
```

iOS solo puede compilarse y firmarse en macOS con Xcode.

Agregue credenciales fuera de Git:

- `android/app/google-services.json`
- `ios/Runner/GoogleService-Info.plist` mediante Xcode
- `ios/Runner/alarm.aiff` ya pertenece a Copy Bundle Resources
- perfil de firma Android mediante `SEISMIK_KEYSTORE*`
- firma/capabilities APNs en el target Runner

Ejecute:

```bash
flutter run \
  --dart-define=SEISMIK_API_BASE_URL=https://api.su-dominio.example \
  --dart-define=SEISMIK_DEVICE_KEY=clave-bootstrap
```

En release, la app activa Play Integrity y App Attest con fallback DeviceCheck;
en debug usa el proveedor App Check de depuración. Registre los debug tokens solo
en proyectos Firebase no productivos.

### DSP móvil

`userAccelerometerEventStream` ya excluye gravedad. Se calcula
`sqrt(x²+y²+z²)`, se compara con 0.39 m/s² (0.04 g) y se estima la varianza de una
ventana de 2.5 s para rechazar movimiento continuo del usuario. Si el dispositivo
está cargando se permite capturar con más sensibilidad; el backend aún requiere
diez dispositivos únicos cercanos, por lo que un teléfono nunca crea una alerta.

iOS no permite ejecución arbitraria y continua del acelerómetro en segundo plano.
Android exige un foreground service visible para monitoreo prolongado; este
cliente inicia DSP durante la sesión activa. No se debe presentar el crowdsourcing
móvil como reemplazo de estaciones físicas ni eludir políticas de batería.

### Alertas críticas: límites del sistema operativo

- Apple debe aprobar el entitlement
  `com.apple.developer.usernotifications.critical-alerts`; se declara en
  `Runner.entitlements`, no en `Info.plist`. Sin aprobación/permiso, iOS degrada la
  alerta. El payload solicita sonido crítico a volumen 1.0.
- Android crea el canal `seismic_critical_alerts` en runtime con importancia
  máxima y full-screen intent. Desde Android moderno el usuario conserva control
  sobre canales, DND y permiso de pantalla completa.
- Ninguna app puede garantizar por código volumen máximo ni saltarse silencio/DND
  sin los permisos, entitlement y decisiones del usuario establecidos por cada OS.

Los sonidos nativos están en `ios/Runner/alarm.aiff` y
`android/app/src/main/res/raw/alarm.wav`.

### Reportes de percepción y daños

La pantalla principal y el detalle de cada evento permiten informar si se sintió
el sismo y describir daños o peligros. El payload se firma con el token individual,
se limita por dispositivo y entra a streams durables separados:

- `stream:seismik:felt-reports`
- `stream:seismik:damage-reports`

La ubicación aproximada es el valor predeterminado. Con consentimiento, la app
muestra el canal oficial aplicable (SGC, IGN, NRCan o USGS DYFI) y abre su
formulario en el navegador. Seismik no lo completa ni lo envía automáticamente.
Los reportes de daños no sustituyen una llamada a emergencias. Detalles de datos,
privacidad y extensión de agencias: `docs/REPORTES_CIUDADANOS.md`.

## Proyecto abierto

El código se publica bajo Apache-2.0. Consulte `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md`, `SECURITY.md` y `GOVERNANCE.md` antes de contribuir.

## Datos globales y reportes oficiales

`config.global.json` contiene estaciones activas descubiertas por FDSN y
proveedores SeedLink abiertos. Ningún proveedor, incluido GEOFON, garantiza todas
las estaciones o todos los países sin excepción: cobertura, canales, licencias y
disponibilidad cambian. Seismik usa múltiples redes y debe monitorizar lag y salud
por estación.

`official_sources.json` configura fuentes gubernamentales para la actualización
posterior. Respete atribución, términos, límites y disponibilidad de cada entidad;
la falta de un reporte oficial nunca debe inventar magnitud, profundidad o fuente.

## Antes de producción

1. Sustituir secretos y montar `.p8`/Firebase Admin como secretos, nunca imágenes.
2. Terminar TLS, WAF, rate limiting y protección anti-DDoS en el edge.
3. Usar Redis HA persistente, backups y nombres de consumidor únicos.
4. Calibrar STA/LTA y PGA por geología, sensor, ruido cultural y tasa de muestreo.
5. Ejecutar replay de formas de onda, shadow traffic y simulacros sin push real.
6. Medir latencia extremo a extremo, falsos positivos/negativos y pérdida de datos.
7. Obtener entitlements, acuerdos y certificación aplicables antes de alertar público.
8. Completar el plan Scrum y registrar una decisión Go/No-Go; aprobar el MVP
   experimental no autoriza por sí solo alertas públicas ni automatización física.
