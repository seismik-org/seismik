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

**Sprint 3 cerrado técnicamente (2026-08-27):** contratos OpenAPI estrictos,
ingesta HMAC idempotente, Redis Streams/DLQ y pipeline MiniSEED → API → Redis →
dispatcher verificados con Docker Compose real. El modo `dry_run` produjo un
payload crítico marcado `TEST`, suprimió el duplicado y no envió ningún push
externo. La evidencia reproducible está en
[`docs/evidence/sprint3-docker-e2e.json`](docs/evidence/sprint3-docker-e2e.json).

**Sprint Añadido 1 en curso (2026-08-30):** la API Platform incorpora portal
OAuth, claves revocables almacenadas como hash, alcances, cuotas y auditoría. El
portal y la API ya están desplegados; resta sincronizar el secreto OAuth web y
cerrar la prueba E2E con una clave temporal revocada al finalizar. Todas las
rutas humanas de datos (`/v1/events/*` y `/v1/network/*`) están cerradas por
defecto y requieren `X-Seismik-API-Key`; la falta de configuración nunca las
convierte en públicas. Salud, OAuth, webhooks internos y dispositivos conservan
sus mecanismos separados porque son puntos de control, no APIs de consulta.

**Sprint 4 móvil avanzado (2026-08-29):** la versión móvil 0.6.2 consume la paleta
Material You completa publicada por Android/One UI, respeta barras e insets del
sistema y convierte Configuración en preferencias persistentes y funcionales.
Incluye Google Maps y navegación para Historial, Sismo sentido, Daños y
Configuración. El historial agrega SGC, USGS y otras fuentes oficiales con caché
offline, atribución y filtros. El reporte “¿Lo sentiste?” permite
elegir una o varias organizaciones geológicas para cada sismo, conserva la
preferencia localmente y usa un catálogo de respaldo sin red. Seismik nunca
envía datos a esas entidades de forma automática: abre sus formularios oficiales
después del consentimiento. La cola completa de reportes offline y las pruebas
en dos dispositivos Android siguen pendientes.

La beta 0.6.3 recupera el evento que inició Android mediante una alerta de
pantalla completa, ofrece autorización explícita para ese acceso en Android
14+ y agrega una simulación local que no publica ni distribuye un sismo. Android
puede degradar la alerta a un banner si el usuario no concede ese acceso.

**Beta técnica GCP 0.4.1 validada (2026-08-29):** Redis y FastAPI reportaron
`healthy`/`ready` en la VM `seismik-beta-01`. El detector abrió SeedLink v4.0,
recibió miles de muestras de estaciones CM de Colombia y CX de Chile, y ejecutó
STA/LTA en modo sombra. La API se publicó detrás de Cloudflare y Caddy en
`https://api.seismik.org`, con el origen restringido a la red de Cloudflare y
TLS `Full (strict)`. Algunas estaciones configuradas no entregaron datos y deben
depurarse durante la calibración. Push continúa deshabilitado; esta prueba no
cambia el estado **No-Go público**.

## Gobierno, Scrum y control de avance

La fuente compartida y verificable de planificación se encuentra en
[`docs/project-management/`](docs/project-management/README.md). Contiene fuentes
Markdown revisables en Git y copias formales en Word:

- Documento maestro del proyecto, alcance y hoja de ruta.
- Plan Scrum de ocho sprints, responsables, entregables y checkpoints.
- Control de avance, riesgos, decisiones, impedimentos y checklist Go/No-Go.

Las fotografías, los videos, la expansión mundial, las alertas públicas
automáticas y las integraciones IoT quedan fuera del MVP inicial. iOS entró en el
Sprint Añadido 2 como beta cerrada: el proyecto está preparado, pero compilar,
firmar y aprobar las Critical Alerts de Apple exige macOS y decisiones externas.
Todo simulacro debe permanecer restringido a testers autorizados y marcado
visiblemente como `TEST` o `SIMULACRO`.

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
- `src/dispatcher/policy.py`: deduplicación, enfriamiento y umbrales por
  dispositivo antes de tocar APNs/FCM.
- `mobile_app/`: aplicación Flutter por capas, App Check, DSP local, mapas y UI.

## Enlace detector → API de eventos

El detector firma cada candidato con HMAC-SHA256 sobre `timestamp.cuerpo` y
lo entrega a `POST /v1/events/candidate`; las asociaciones oficiales viajan a
`POST /v1/events/official-update`.

El hilo que recibe paquetes SeedLink nunca se bloquea esperando a la API. Si
la entrega falla, el evento se persiste en una cola en disco
(`SEISMIK_ALERT_SPOOL_DIR`) con escritura atómica y se reintenta en orden.
La respuesta de la API decide el destino del evento:

| Respuesta | Decisión |
|---|---|
| 2xx | Entregado; `duplicate=true` se contabiliza aparte |
| 5xx, 408, 429 o error de red | Reintento con la cola durable |
| Resto de 4xx | Descarte con registro: repetir sólo repetiría el rechazo |

Un evento que supera `spool_max_age_seconds` (15 minutos por defecto) se
descarta: dejó de ser accionable mucho antes. La sonda del detector publica
entregados, duplicados, pendientes y último error en `/health/ready`.

```bash
docker compose --profile detector up --build
curl -s http://localhost:8080/health/ready
```

## Alertas en tiempo real

Tres decisiones separan un aviso útil de una avalancha de notificaciones, y
las tres viven en `src/dispatcher/policy.py`:

1. **Deduplicación por evento.** `seismik:alert:sent:<tipo>:<event_id>` se
   reclama con `SET NX` durante `SEISMIK_ALERT_DEDUP_SECONDS`. Un reinicio
   del dispatcher reentrega el mensaje del stream, pero no la alerta.
2. **Enfriamiento por zona.** `seismik:alert:cooldown:<zona>` se reclama
   **antes** de enviar el push, no después: dos dispatchers en paralelo no
   pueden alertar la misma zona. Si el envío falla de forma inesperada, la
   reclamación se libera para que el stream vuelva a intentarlo.
3. **Umbrales por dispositivo.** Suscripción a alertas tempranas y oficiales,
   magnitud mínima y radio elegido por la persona, siempre acotado por la
   geocerca de la plataforma (`SEISMIK_GEOFENCE_RADIUS_KM`).

Las actualizaciones oficiales se deduplican pero no se enfrían: una revisión
de magnitud debe llegar aunque el candidato haya alertado segundos antes.

Cada alerta emitida se anota en `stream:seismik:alert-ledger`. La app la
consulta con `GET /v1/alerts/recent?device_id=…&since=<cursor>` para
recuperar lo que ocurrió mientras el teléfono estuvo sin conexión; el
servidor reaplica los mismos filtros de ese dispositivo.

## Simulacros y eventos simulados

`tools/simulate_event.py` inyecta un sismo simulado por la ruta real —API
firmada, bus, dispatcher y filtros— sin endpoints especiales de prueba. Todo
identificador de simulacro empieza por `drill-`, de modo que la evidencia
nunca se confunde con una detección real.

```bash
python tools/simulate_event.py --profile bogota --dry-run
python tools/simulate_event.py --profile bogota \n  --base-url http://127.0.0.1:8000 --secret "$SEISMIK_WEBHOOK_HMAC_SECRET"
```

Un destino que no sea local exige `--confirm-production`: un simulacro contra
un entorno con push habilitado envía notificaciones de verdad.

`tools/run_drill.py` ejecuta el ensayo completo sin depender de Docker: levanta
la API con uvicorn en un puerto local, registra cuatro dispositivos con umbrales
distintos, inyecta el sismo firmado, consume el stream con el dispatcher real y
consulta la bitácora de alertas de cada dispositivo. Sólo Redis se sustituye por
`fakeredis`, y la evidencia lo declara.

```bash
# Sismo simulado
python tools/run_drill.py --profile bogota --output data/drills/drill.json

# Onda real grabada, a través del detector STA/LTA
python tools/run_drill.py --replay-case co-2023-08-17-m6.1 --output data/drills/m61.json

# Ruido ambiental: el silencio es el resultado esperado
python tools/run_drill.py --replay-case co-2026-08-24-ambient --expect-silence   --output data/drills/ambient.json
```

Evidencia registrada en `data/drills/` (2026-08-30):

| Ensayo | Alerta crítica | Actualización oficial |
|---|---|---|
| Simulado `bogota` | cerca, umbral-alto | cerca, silenciado |
| Replay M7.4, M6.1 y M5.7 | cerca, umbral-alto | — |
| Ruido ambiental | ninguna | — |

En los tres sismos reales el dispositivo fuera del radio elegido nunca aparece, y
en el caso de ruido ambiental hubo disparos locales de hasta 16.3 de razón
STA/LTA en `CM.PRA` que la coincidencia multiestación descartó sin alertar.

### Salud de los proveedores SeedLink

`tools/measure_seedlink_health.py` recorre los proveedores habilitados y mide
tiempo de conexión TCP, tiempo hasta el primer paquete, lag de ese paquete y la
recuperación tras reconectar. Con eso el orden de respaldo se decide con datos:

```bash
python tools/measure_seedlink_health.py --config config.json   --output data/seedlink/provider-health.json
```

Medición del 2026-08-31 (`data/seedlink/sa2-provider-health-2026-08-30.json`):

| Proveedor | TCP | Estaciones que entregan | Lag mediano | Reconexión |
|---|---:|---:|---:|---|
| `earthscope_colombia` | 0.16 s | 1 de 2 | 6.12 s | recuperó con 3.75 s de lag |
| `geofon_chile` | 0.25 s | 1 de 2 | 1.24 s | no aplicada |

Es una medición puntual, no un acuerdo de disponibilidad. Dos observaciones que
importan para alerta temprana: el primer paquete tardó entre 39 y 45 s en llegar
tras conectar, y dos de las cuatro estaciones probadas no entregaron nada dentro
de la ventana de 45 s.

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
- `stream:seismik:integrations` (salida durable para organizaciones)
- `stream:seismik:integrations-dead-letter`

## Seguridad

Los webhooks y pings firman exactamente `timestamp + "." + raw_body` con
HMAC-SHA256:

- `X-Seismik-Timestamp`
- `X-Seismik-Signature`
- `X-Seismik-Device-Session` para solicitudes posteriores de una instalación verificada

El registro exige `app_attest_token` en iOS o `play_integrity_token` en Android.
Esos campos transportan un **Firebase App Check token** corto respaldado por App
Attest/DeviceCheck o Play Integrity; el servidor lo verifica con Firebase Admin.
Tras verificar App Check, el servidor emite un token de sesión aleatorio por
instalación. Sólo conserva su hash, lo rota al registrar de nuevo el dispositivo
y no se incluye ninguna clave compartida en el APK o IPA.

En producción, `SEISMIK_INTEGRITY_VERIFICATION_ENABLED=true` es obligatorio por
validación de configuración. Restrinja también los Firebase App IDs permitidos.

## Integraciones oficiales e IoT (Sprint 6)

Las actualizaciones gubernamentales se normalizan como
`official_report_update`; incluyen fuente, magnitud, profundidad, ubicación y
enlace de atribución. La app y los consumidores externos pueden diferenciar
claramente un candidato preliminar (`earthquake_candidate`) de una confirmación
oficial.

### Cobertura SeedLink preliminar y lectura de ondas

La configuración beta activa grupos de estaciones en **Colombia**, norte de
**Chile**, **Indonesia/Sunda** y **Europa central**. EarthScope ofrece su
servicio SeedLink público y GEOFON publica aproximadamente 300 estaciones en
tiempo real; cada conexión y estación se vigila antes de utilizarla. No es una
red mundial completa ni un servicio oficial de alerta temprana: los canales,
la telemetría y la disponibilidad pueden variar.

Para cada disparo se conservan la relación STA/LTA, pico de onda en cuentas y
ruido RMS. La app muestra un índice de señal/ruido por candidato. **No convierte
cuentas crudas a magnitud**: hacerlo requiere deconvolucionar la respuesta de
cada instrumento, localizar el evento y calibrar el modelo contra catálogos
oficiales regionales. Por eso `magnitude_estimate` permanece nulo con estado
`pending_station_calibration` hasta validar científicamente una red; ese campo
nunca participa en el envío de alertas.

Las organizaciones autenticadas en el portal pueden crear un webhook HTTPS en
`POST /v1/developer/webhooks`. Seismik muestra el secreto de firma una sola vez.
Cada entrega usa HMAC SHA-256 sobre `timestamp + "." + cuerpo` y lleva los
encabezados `X-Seismik-Event-Id`, `X-Seismik-Delivery-Id`,
`X-Seismik-Timestamp` y `X-Seismik-Signature`. Sólo se aceptan destinos HTTPS
que resuelvan a direcciones públicas, para impedir SSRF contra la red interna.

El canal actual es **exclusivamente de simulación**. Cada payload declara
`safety_mode: simulation_only` y prohíbe controlar equipos físicos. Es apto para
tableros, simulacros, investigación y pruebas de integración; no es una orden
para ascensores, gas, agua ni electricidad. Una futura automatización de
infraestructura exige evaluación de seguridad funcional, acuerdos con los
operadores, interlocks locales y aprobación científica/regulatoria.

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

Variables del alertamiento en tiempo real (ver `.env.example`):

| Variable | Efecto |
|---|---|
| `SEISMIK_ALERT_COOLDOWN_SECONDS` | Enfriamiento por zona entre alertas críticas |
| `SEISMIK_ALERT_DEDUP_SECONDS` | Ventana en la que un `event_id` no vuelve a alertar |
| `SEISMIK_ALERT_LEDGER_MAXLEN` | Tamaño de la bitácora consultable por la app |
| `SEISMIK_ALERT_RECENT_LIMIT` | Alertas devueltas por `GET /v1/alerts/recent` |
| `SEISMIK_GEOFENCE_RADIUS_KM` | Radio máximo que puede pedir un dispositivo |
| `SEISMIK_ALERT_SPOOL_DIR` | Cola durable del detector (proceso detector) |

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
  --dart-define=SEISMIK_API_BASE_URL=https://api.su-dominio.example
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

### Umbrales elegidos por la persona

En Configuración se ajustan cuatro filtros que viajan al servidor en el registro
del dispositivo y los aplica el dispatcher, no la app:

| Ajuste | Efecto |
|---|---|
| Alertas tempranas | Recibir o no candidatos multiestación antes del reporte oficial |
| Actualizaciones oficiales | Recibir o no la revisión publicada por una entidad geológica |
| Magnitud mínima | Descarta actualizaciones oficiales por debajo del umbral |
| Umbral de cercanía | Descarta avisos cuyo epicentro esté fuera del radio elegido |

Cambiar cualquiera de ellos vuelve a registrar el dispositivo: sin ese paso el
filtro nuevo no llegaría al dispatcher. El radio se acota siempre por la geocerca
de la plataforma, de modo que nadie amplía su alcance más allá de la política.

Un candidato sin epicentro estimado no se filtra por distancia: excluir por una
posición desconocida silenciaría una alerta real.

### Historial cartográfico y epicentros

El historial es un mapa a pantalla completa con marcadores de eventos oficiales y
de estaciones. La hoja inferior se arrastra entre tres posiciones fijas —16 %,
36 % y 86 %— y el mapa permanece operable en todas. Tocar un marcador selecciona
el evento en la lista y centra la cámara; tocar el mapa deselecciona.

«Abrir epicentro» usa el proveedor elegido en Configuración:

| Preferencia | Orden de intentos |
|---|---|
| Según el sistema | Apple Maps y Google Maps en iOS; intent `geo:` en Android; web al final |
| Google Maps | `comgooglemaps://` en iOS, `geo:` en Android, web al final |
| Apple Maps | Apple Maps en iOS; en Android sólo el respaldo web |

Android 11+ oculta las apps instaladas salvo las declaradas en `<queries>`, e iOS
sólo permite consultar los esquemas de `LSApplicationQueriesSchemes`. Ambos
manifiestos los declaran; sin ellos, la acción caería siempre al respaldo web.

### Funcionamiento sin conexión

Un sismo suele dejar a la gente sin datos justo cuando más importa reportar.

- Los reportes de sismo sentido y de daños se guardan en el teléfono cuando el
  envío falla por red. El cuerpo se conserva tal cual se compuso: `report_id` y
  `observed_at` no cambian al reintentar, así que la hora registrada sigue siendo
  la del sismo y el servidor reconoce el reenvío como el mismo reporte.
- La cola se reenvía al recuperar la red, en orden y deteniéndose ante el primer
  fallo transitorio para no gastar batería repitiendo el mismo error.
- Un rechazo definitivo del servidor (4xx de contrato) sale de la cola en lugar
  de reintentarse indefinidamente; también se descartan los reportes con más de
  30 días o 12 intentos.
- Las alertas recibidas mientras el teléfono estuvo sin conexión se recuperan de
  `GET /v1/alerts/recent` y se incorporan al historial sin duplicar.
- El historial oficial ya consultado queda en caché local y se muestra cuando la
  API no responde.

La app indica cuántos reportes esperan conexión y permite reintentar a mano desde
el historial y desde Configuración.

### Compilación y verificación

```bash
cd mobile_app
flutter analyze
flutter test
flutter build apk --release \
  --dart-define=SEISMIK_API_BASE_URL=https://api.su-dominio.example
```

El APK universal de release incluye `arm64-v8a`, `armeabi-v7a` y `x86_64`. La
firma exige `SEISMIK_KEYSTORE`, `SEISMIK_KEYSTORE_PASSWORD`, `SEISMIK_KEY_ALIAS`
y `SEISMIK_KEY_PASSWORD`.

Para verificar sólo que el release compila en una máquina sin acceso al keystore
de producción:

```bash
flutter build apk --release -PseismikUnsignedReleaseCheck=true \
  --dart-define=SEISMIK_API_BASE_URL=https://api.su-dominio.example
```

Ese APK queda firmado con la clave de depuración y **no es distribuible**: la
bandera sólo tiene efecto cuando `SEISMIK_KEYSTORE` está ausente, y Gradle lo
advierte en la salida. El job `android` de CI usa exactamente esta ruta y falla
si el APK deja de incluir las tres ABIs.

Para la distribución firmada, `tools/build-signed-release.ps1` descifra el blob
DPAPI de la contraseña en la sesión de Windows que lo creó, se lo pasa a Gradle
por variables de entorno del proceso y las borra al terminar. La contraseña no se
imprime ni se escribe en disco; al final publica el SHA-256 del artefacto y la
huella del certificado firmante como evidencia:

```powershell
.\tools\build-signed-release.ps1 `
  -Keystore ..\..\work\secrets\seismik-upload.jks `
  -PasswordFile ..\..\work\secrets\seismik-upload-password.dpapi `
  -Alias seismik-upload `
  -ApiBaseUrl https://api.seismik.org
```

El blob DPAPI sólo puede descifrarlo la cuenta de Windows que lo generó, así que
este paso no puede automatizarse en CI ni ejecutarlo otra persona.

### Preparación iOS

iOS sólo puede compilarse y firmarse en macOS con Xcode. El repositorio deja
lista la configuración:

- `Runner.entitlements` declara `com.apple.developer.usernotifications.critical-alerts`.
- `Info.plist` declara `LSApplicationQueriesSchemes` con `comgooglemaps` y `maps`.
- `Flutter/Debug.xcconfig` y `Flutter/Release.xcconfig` incluyen de forma opcional
  un `Seismik.xcconfig` local, ignorado por Git.

```bash
cp ios/Flutter/Seismik.xcconfig.example ios/Flutter/Seismik.xcconfig
# completar SEISMIK_GOOGLE_MAPS_API_KEY y DEVELOPMENT_TEAM
cd ios && pod install && cd ..
flutter build ios --release \
  --dart-define=SEISMIK_API_BASE_URL=https://api.su-dominio.example
```

`GoogleService-Info.plist` se agrega mediante Xcode y no se versiona. Sin la
aprobación de Apple para el entitlement de alertas críticas, iOS degrada la
alerta a una notificación normal.

Como Xcode no existe fuera de macOS, la compilación iOS se verifica en CI: el job
`ios` corre en `macos-latest`, instala los Pods y ejecuta
`flutter build ios --release --no-codesign`, que valida el proyecto Xcode y el
AOT de Dart sin necesidad de certificados. Después comprueba que el bundle
resultante conserve `LSApplicationQueriesSchemes` y el entitlement de alertas
críticas. `pytest tests/test_ios_configuration.py` valida los plists desde
cualquier sistema operativo.

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
