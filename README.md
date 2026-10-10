# Seismik

[![CI](https://github.com/seismik-org/seismik/actions/workflows/ci.yml/badge.svg)](https://github.com/seismik-org/seismik/actions/workflows/ci.yml)
[![Código visible · uso restringido](https://img.shields.io/badge/licencia-c%C3%B3digo_visible_%C2%B7_uso_restringido-blue)](LICENSE)

Plataforma de información sísmica, aplicaciones móviles y API para desarrolladores.
Seismik reúne catálogos sismológicos, conserva la atribución de cada evento y
desarrolla detección experimental mediante ondas y señales voluntarias de dispositivos.

**Estado: beta en desarrollo. Última revisión: 10 de octubre de 2026.**
El portal y la API están desplegados. Android utiliza Flutter y Material 3;
la interfaz de iOS es nativa en SwiftUI. Los planes comerciales están publicados,
pero el checkout y los cobros automáticos siguen desactivados.

### Estado comprobado

- **Android 1.0.0 (61):** disponible en la prueba interna de Google Play.
- **iOS 1.0.0 (61):** disponible en TestFlight interno. Apple aprobó Critical
  Alerts para la app y se verificó el entitlement en el binario firmado.
  Cada persona todavía debe conceder el permiso en su iPhone.
- **Alertas y familia:** alarma Android al recibir la notificación, acción
  «Silenciar» y ubicación familiar automática opcional, desactivada por defecto.
  Comparte la última ubicación registrada, aproximada y reciente; no afirma
  que la persona esté a salvo, necesite ayuda ni haya recibido la alerta.
- **Web «¿Lo sentiste?»:** mapa, selección de sismo oficial y reporte de si se
  sintió o no, sin nombre ni correo, con Turnstile y ubicación aproximada por defecto.
  El diseño comparte los temas claro/oscuro del portal.
- **Estado:** comprobaciones periódicas e historial de disponibilidad en el borde;
  no depende de que alguien visite la página.
- **Administración:** MFA y controles de alcance, sesiones, auditoría y privacidad.

Estos canales de prueba no equivalen a una publicación general en ambas tiendas.
La entrega sonora con Android bloqueado y los escenarios de permisos/Focus de
iOS requieren pruebas físicas; las pruebas automatizadas no garantizan el sonido.

> **Seismik es independiente: no representa a ninguna entidad pública ni es un
> servicio oficial o certificado de alerta temprana.** No predice terremotos ni
> garantiza entrega, anticipación o disponibilidad. Los candidatos experimentales
> no equivalen a reportes oficiales. No sustituye las instrucciones de las
> autoridades ni una llamada a emergencias.

## Enlaces

| Recurso | Dirección |
| --- | --- |
| Portal | [seismik.org](https://seismik.org/) |
| Desarrolladores y planes | [devs.seismik.org](https://devs.seismik.org/) |
| Inicio de sesión web | [auth.seismik.org](https://auth.seismik.org/) |
| API | [api.seismik.org](https://api.seismik.org/) |
| Estado de servicios públicos | [status.seismik.org](https://status.seismik.org/) |
| Reportar si sentiste un sismo | [ifeltit.seismik.org](https://ifeltit.seismik.org/) |
| Contacto | [Página de contacto](https://seismik.org/contact/) · [support@seismik.org](mailto:support@seismik.org) |

La página de estado consulta los servicios en tiempo de ejecución; no certifica
la entrega de una alerta a cada teléfono ni la cobertura de estaciones.

## Qué incluye

- **Catálogo sísmico:** eventos recientes, historial de hasta 30 días, filtros y
  enlaces a las fuentes. La disponibilidad depende de cada proveedor.
- **Android:** Flutter con Material 3/Material You, mapas, preferencias,
  notificaciones y reportes ciudadanos.
- **iOS:** SwiftUI nativo, mapas MapKit, registro APNs y preferencias. El proyecto
  conserva infraestructura Flutter y plugins de integración.
- **Portal de desarrolladores:** autenticación centralizada, claves con alcances,
  rotación, revocación, selección de plan y consumo agregado por cuenta.
- **Consumo visible:** cuotas por minuto, día y mes, porcentajes, consultas
  restantes, reinicios UTC y desglose de eventos y estaciones.
- **Procesamiento durable:** ingesta HMAC, Redis Streams, reintentos,
  deduplicación, bitácora de alertas y colas de mensajes fallidos.
- **Investigación y simulación:** detector SeedLink/ObsPy, STA/LTA,
  coincidencia multiestación, replay y crowdsourcing voluntario.
- **Webhooks institucionales:** entregas firmadas para simulación e investigación;
  no autorizan el control de gas, energía, ascensores u otros equipos físicos.

### Límites importantes

Un despliegue exitoso no prueba eficacia científica ni aprobación en las tiendas.
El push depende de red, permisos, configuración del dispositivo y servicios
externos. Las Critical Alerts de iOS requieren aprobación de Apple y permiso del
usuario: declararlas en el proyecto no concede ese derecho. Android también
conserva control sobre notificaciones, sonido, No molestar y pantalla completa.

La calibración, evaluación independiente, redundancia operativa y autorizaciones
aplicables siguen siendo requisitos para cualquier uso de seguridad pública.

La ML propia sigue **sin validación científica** (`failed_validation` en la
evaluación local); la autorización operativa beta no equivale a `validated`.
El detector en producción fue desplegado manualmente desde otra revisión y
su integración completa de ML no está reconciliada con `main`. No redesplegarlo
por CD desde este árbol sin verificar calibraciones, configuración y contratos
de transporte. No se habilitan alertas a usuarios sólo por disponer de una ML.

## API y planes

### Prueba sin cuenta

```bash
curl "https://api.seismik.org/v1/public/showcase-events?limit=6"
```

Este endpoint independiente no requiere clave. Publica eventos oficiales con
umbral, límite y cuota por IP configurados por el servidor; la respuesta incluye
el umbral aplicado. No ofrece los filtros de la API autenticada.

### Consulta con clave

Crea una clave en el [portal](https://devs.seismik.org/#panel). Guárdala en tu
servidor, nunca en una app pública ni en código del navegador.

```bash
curl "https://api.seismik.org/v1/events/history?days=7&minimum_magnitude=4" \
  -H "X-Seismik-API-Key: TU_CLAVE_API"
```

| Ruta | Acceso |
| --- | --- |
| `GET /v1/public/showcase-events` | Público, limitado por IP |
| `GET /v1/events/history` | Clave con `events:read` |
| `GET /v1/events/recent` | Clave con `events:read` |
| `GET /v1/network/stations` | Clave con `stations:read` |
| `GET /v1/developer/account` | Sesión del titular o identidad verificada; no basta una clave API |

Las instalaciones móviles verificadas tienen una sesión separada.
Consulta los contratos en [OpenAPI](docs/api/openapi-v1.json).

### Catálogo de planes

Precios de lista en USD antes de impuestos. Las cuotas se comparten entre todas
las claves de una cuenta; los límites gratuitos pueden configurarse al desplegar.

| Plan | Precio | Consultas/mes | Por minuto | Por día | Claves activas |
| --- | --- | ---: | ---: | ---: | ---: |
| Always Free with API Key | Gratis | 30.000 | 60 | 10.000 | 3 |
| Pay-as-you-go | Saldo desde US$5 | 1.000.000 | 300 | 100.000 | 10 |
| Pro | US$19/mes | 50.000 | 120 | 10.000 | 5 |
| Max | US$49/mes | 150.000 | 240 | 20.000 | 10 |
| Ultra | US$129/mes | 400.000 | 360 | 40.000 | 20 |
| Enterprise | A negociar | Por acuerdo | Por acuerdo | Por acuerdo | Por acuerdo |

Pay-as-you-go publica US$0,0005 por consulta de eventos y US$0,001 por consulta
de estaciones, con paquetes de saldo US$5/25/100. Su cuota mensual es un límite
operativo, **no un paquete de un millón de consultas por US$5**. Pro, Max y Ultra
incluyen las consultas dentro de sus cuotas, sin excedentes automáticos.

**Durante la beta no se cobra ni se descuenta saldo por uso.** Elegir un plan
guarda una preferencia: no activa una suscripción ni concede nuevas cuotas.
La activación se acuerda con Seismik; Enterprise no es ilimitado por defecto.
Al superar una cuota, la API devuelve `429`. Los días y meses se reinician en UTC
y las consultas no utilizadas no se acumulan.

Minuto y día incluyen intentos autenticados rechazados por cuota. El mes cuenta
solicitudes que pasan las cuotas, no necesariamente respuestas exitosas.
Ninguno de estos contadores representa cargos actuales. Más detalles en
[planes por cuenta](docs/developer-plans.md) y
[supuestos económicos](docs/developer-pricing-economics.md).

## Fuentes y atribución

El catálogo configurable incluye [USGS](https://earthquake.usgs.gov/earthquakes/),
[EMSC/CSEM](https://www.emsc-csem.org/Earthquake_information/),
[INGV](https://terremoti.ingv.it/), [GeoNet](https://www.geonet.org.nz/earthquake),
[BMKG](https://data.bmkg.go.id/gempabumi/),
[JMA](https://www.jma.go.jp/bosai/map.html#contents=earthquake_map),
[SGC](https://www.sgc.gov.co/sismos) e [IGP](https://ultimosismo.igp.gob.pe/).

Estar configurado no garantiza que un feed esté disponible o habilitado en cada
entorno. Los eventos conservan agencia y enlace de atribución; no se deben
inventar magnitud, profundidad o confirmación cuando faltan datos.
Configuración: [official_sources.json](official_sources.json).

## Arquitectura y organización

```text
Fuentes oficiales / SeedLink → catálogo y detector experimental
                                        ↓ HMAC
Web / apps móviles → API FastAPI ↔ Redis / Streams
                                        ↓
                         dispatcher e integraciones
                             ↓                 ↓
                         APNs / FCM       webhooks firmados
```

| Carpeta | Responsabilidad |
| --- | --- |
| `src/api/` | API, identidad, dispositivos, claves, planes y medición |
| `src/eew/` | Catálogos, adquisición, DSP, detección y replay |
| `src/dispatcher/` | Política de entrega, reintentos, push e integraciones |
| `src/crowdsourcing/` y `src/reporting/` | Señales voluntarias y reportes ciudadanos |
| `mobile_app/lib/` | Cliente Flutter, principalmente la interfaz Android |
| `mobile_app/ios/Runner/Native/` | Interfaz, estado y servicios SwiftUI de iOS |
| `web/` | Portal, autenticación, desarrolladores, contacto y estado |
| `deploy/` y `.github/workflows/` | Infraestructura y automatización |
| `tests/`, `tools/`, `docs/` | Pruebas, utilidades y documentación |

La API y el portal se despliegan en Cloud Run detrás del enrutamiento de
Cloudflare. El worker combinado ejecuta dispatcher e integraciones en un mismo
servicio. El detector y Redis tienen necesidades de persistencia distintas;
Docker Compose local no reproduce toda la infraestructura productiva.

## Desarrollo local

Los procedimientos siguientes son para mantenedores o personas con autorización
escrita de uso. La visibilidad del repositorio no concede permiso para operar una
réplica del servicio; consulta [la licencia](LICENSE).

### Backend con Docker Compose

Copia `.env.example` a `.env`, configura valores locales y mantén
`SEISMIK_PUSH_ENABLED=false` y `SEISMIK_PUSH_MODE=dry_run`.
No uses secretos ni credenciales de producción para pruebas locales.

```bash
docker compose up --build
curl "http://127.0.0.1:8000/health/ready"
```

La API queda en `http://127.0.0.1:8000`; documentación interactiva en `/docs`.
Detector opcional: `docker compose --profile detector up --build`.

### Backend con Python

Requiere Python 3.12 o posterior y Redis accesible. En PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt
.venv\Scripts\python.exe -m pip install -e .
$env:SEISMIK_REDIS_URL = 'redis://127.0.0.1:6379/0'
$env:SEISMIK_PUSH_ENABLED = 'false'
$env:SEISMIK_PUSH_MODE = 'dry_run'
.venv\Scripts\seismik-api.exe
```

Configura las demás variables según `.env.example`. Fuera de Compose, las rutas
de credenciales y el host `redis` del ejemplo necesitan adaptación.
Producción valida requisitos más estrictos.

### Pruebas y simulación

```bash
python -m pytest
python -m ruff check src tests
python -m mypy src
python tools/run_drill.py --profile bogota --output data/drills/local.json
```

El simulacro local no envía push externo. Los ensayos no constituyen validación
sismológica independiente. No inyectes eventos en producción ni habilites push
real sin autorización y destinos de prueba explícitos.

### Móvil

CI usa Flutter 3.47.1. Para analizar el cliente Flutter:

```bash
cd mobile_app
flutter pub get
flutter analyze
flutter test
```

Android necesita configuración Firebase, App Check/Play Integrity y una clave
Google Maps restringida al paquete y certificado apropiados. Un APK fuera de
Google Play puede no satisfacer la política de integridad de producción.
iOS requiere macOS, Xcode, Firebase, APNs y perfiles de firma; sus vistas nativas
están en `ios/Runner/Native/` y sus pruebas en `RunnerTests/`.
Los trabajos de compilación de CI no equivalen a una publicación en las tiendas.

No versiones `google-services.json`, `GoogleService-Info.plist`, claves `.p8`,
keystores ni contraseñas. Consulta [la guía móvil](mobile_app/README.md),
contrastando sus notas históricas con el código y los workflows actuales, y
[las pruebas de iPhone](docs/PRUEBAS_IPHONE.md).

## Seguridad y despliegue

- Claves API revocables almacenadas como hash y alcances por producto.
- Sesiones separadas para el portal y para instalaciones móviles verificadas.
- Firmas HMAC sobre el cuerpo original, idempotencia y auditoría de ingesta.
- Turnstile y protección del edge para operaciones humanas; no sustituyen
  autenticación ni cuotas de solicitudes máquina a máquina.
- Secretos fuera de Git e imágenes; configuración productiva con permisos mínimos.

Consulta [Cloud Run](deploy/CLOUD_RUN.md),
[despliegue desde GitHub](deploy/GITHUB_ACTIONS.md),
[protección contra abuso](docs/CLOUDFLARE_ABUSE_PROTECTION.md) y
[política de seguridad](SECURITY.md). CI verifica backend, Flutter, Android e iOS,
incluidas pruebas nativas, y despliega los servicios afectados cuando corresponde.
Las guías de sprints son referencias históricas: verifica la configuración y
el código vigente antes de ejecutar comandos de producción.

## Documentación y colaboración

- [Reportes ciudadanos, consentimiento y privacidad](docs/REPORTES_CIUDADANOS.md).
- [Reportes web y Google Maps](docs/IFELTIT.md).
- [Historial público de disponibilidad](docs/STATUS_HISTORY.md).
- [Alertas, familia y Critical Alerts](docs/mobile-alert-family-critical-alerts-2026-10-09.md).
- [Planificación y evidencias](docs/project-management/README.md): documentos
  fechados, no un indicador automático del estado actual.
- [Referencia histórica de ingeniería](ENGINEERING_NOTES_LEGACY.md): README
  anterior, conservado para no perder procedimientos y mediciones.
- [Contribuir](CONTRIBUTING.md), [gobernanza](GOVERNANCE.md) y
  [código de conducta](CODE_OF_CONDUCT.md).

## Licencia y privacidad del repositorio

El material original nuevo se publica bajo [Seismik Source-Visible License 1.0](LICENSE):
consulta y estudio, sin permiso para desplegar, redistribuir o ofrecer una réplica
del código cubierto, salvo acuerdo escrito. **No es una licencia open source.**
GitHub permite ver y hacer forks dentro de su plataforma; eso no concede por sí
solo permiso para operar el software. No se restringen implementaciones independientes,
ideas generales ni usos que la ley permita.

Los permisos irrevocables de versiones previamente publicadas bajo Apache-2.0
se conservan, al igual que los derechos de terceros y contribuyentes. La licencia
anterior está en [docs/licenses/Apache-2.0.txt](docs/licenses/Apache-2.0.txt).
Las fuentes externas, marcas y datos tienen términos separados. Las aplicaciones
y la API oficiales se rigen por sus propios términos de servicio.

No publiques credenciales, perfiles de firma, tokens, correos personales,
identificadores de dispositivos ni ubicaciones de personas. `.gitignore` y las
pruebas preventivas ayudan, pero borrar un archivo no retira una credencial del
historial: se requiere evaluar su rotación y limpiar las referencias afectadas.
