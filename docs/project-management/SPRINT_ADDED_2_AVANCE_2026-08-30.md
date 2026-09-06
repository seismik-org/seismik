# Seismik — avance Sprint Añadido 2

Versión: 0.1
Fecha de corte: 2026-08-30 (America/Bogota)
Estado: cierre técnico de implementación; simulacro cerrado en Android/iOS y
revisión científica pendientes de ejecución con personas y dispositivos reales.

## Objetivo

Conectar el detector SeedLink/STA-LTA con la API de eventos, activar alertas en
tiempo real sobre Redis Streams con deduplicación y enfriamiento, y completar la
aplicación Flutter (Android e iOS) con umbrales de aviso, historial cartográfico,
apertura del epicentro en mapas, reportes ciudadanos y funcionamiento sin
conexión con sincronización posterior.

Este Sprint **no** habilita alertas públicas certificadas, ni Critical Alerts de
Apple aprobadas, ni push en producción: todo se entrega en modo cerrado.

## Avance por actividad

| ID | Estado | Resultado actual |
|---|---|---|
| SA2-01 | Completo técnico | El detector entrega candidatos con firma HMAC y cola durable; `tools/measure_seedlink_health.py` midió conexión, primer paquete, lag y reconexión contra los proveedores reales y ordenó el respaldo con esos datos |
| SA2-02 | Avanzado | Política versionada en código y verificada con tres sismos reales grabados (M7.4, M6.1 y M5.7) y un caso de ruido ambiental que no disparó. La revisión formal del asesor científico sigue pendiente |
| SA2-03 | Completo técnico | Ruta candidato → API → Redis Streams → dispatcher → push verificada de extremo a extremo con eventos simulados; el push permanece en `dry_run` con allowlist |
| SA2-04 | Completo técnico | La persona elige alertas tempranas, actualizaciones oficiales, magnitud mínima y umbral de cercanía; el cambio se vuelve a registrar en el servidor y el dispatcher lo aplica |
| SA2-05 | Avanzado | Proyecto iOS completo y validado estáticamente por pruebas; CI compila iOS en `macos-latest` con `--no-codesign`. La firma y la prueba en un iPhone real siguen exigiendo cuenta Apple y dispositivo del equipo |
| SA2-06 | Completo técnico | Selector de proveedor cartográfico con Apple Maps, Google Maps o decisión del sistema; ambos abren el mismo epicentro y existe respaldo web |
| SA2-07 | Completo técnico | Historial como mapa interactivo a pantalla completa con marcadores de eventos y estaciones; tocar un marcador selecciona el evento sin bloquear el mapa |
| SA2-08 | Completo técnico | Hoja inferior deslizable con tres posiciones fijas; el mapa permanece operable y la selección se sincroniza en ambos sentidos |
| SA2-09 | Completo técnico | Acción «Abrir epicentro» en detalle, historial y alerta crítica, con respaldo web cuando no hay app instalada |
| SA2-10 | Avanzado | `tools/run_drill.py` ejecutó cuatro ensayos sobre HTTP real con evidencia en `data/drills/`; el shadow run continuo y el simulacro con testers y teléfonos reales requieren decisión del Product Owner |

## Qué se construyó

### Enlace detector → API de eventos

- `src/eew/delivery.py`: cola durable en disco con escritura atómica, límite de
  entradas, vencimiento por antigüedad y contadores de entrega.
- `src/eew/alerts.py`: clasifica la respuesta de la API. Un 5xx, 408 o 429 se
  reintenta; un 4xx de contrato se descarta con registro, en lugar de repetirse.
- `src/runtime_health.py`: la sonda del detector publica entregados, duplicados,
  pendientes en cola y último error.
- `docker-compose.yml`: el servicio `detector` monta un volumen persistente para
  la cola, de modo que un reinicio de la API no pierda candidatos.

### Alertas en tiempo real

- `src/dispatcher/policy.py`: deduplicación por evento y enfriamiento por zona
  reclamados con `SET NX` **antes** de enviar el push, y liberados si el envío
  falla de forma inesperada para que el stream vuelva a intentarlo.
- Filtros por dispositivo: suscripción, magnitud mínima y radio elegido por la
  persona, acotado siempre por la geocerca de la plataforma.
- `src/api/alerts.py`: `GET /v1/alerts/recent` devuelve la bitácora de alertas
  ya emitidas, filtrada con los mismos criterios, para que una app que estuvo
  sin conexión recupere lo que se perdió.

### Aplicación Flutter

- Umbral de magnitud y umbral de cercanía persistentes; al cambiarlos, la app
  vuelve a registrar el dispositivo para que el filtro llegue al dispatcher.
- Historial como mapa interactivo con hoja inferior deslizable de tres
  posiciones y selección cruzada entre marcador y lista.
- «Abrir epicentro» con Apple Maps, Google Maps o el criterio del sistema, con
  respaldo web y avisos declarados en `AndroidManifest.xml` e `Info.plist`.
- Reportes de sismo sentido y de daños con cola offline persistente: el cuerpo
  se guarda tal cual se compuso, conserva `report_id` y `observed_at`, y se
  reenvía al recuperar la red sin crear duplicados.

## Validación de esta iteración

- Backend: 140 pruebas aprobadas (66 antes del Sprint).
- Ruff: sin hallazgos.
- mypy: sin hallazgos en 42 archivos fuente.
- CI: cuatro jobs (`backend`, `mobile`, `android`, `ios`); el YAML se valida en pruebas.
- Flutter `analyze`: sin hallazgos.
- Flutter `test`: 46 pruebas aprobadas.
- Android: APK universal de depuración y de release compilados; el release
  incluye `arm64-v8a`, `armeabi-v7a` y `x86_64`.
- Simulacros: eventos simulados atraviesan API firmada, bus, dispatcher y
  filtros por dispositivo; un evento repetido, uno alterado y uno fuera del
  radio elegido quedan cubiertos por pruebas.

## Evidencia de campo incorporada

### Proveedores SeedLink (`data/seedlink/sa2-provider-health-2026-08-30.json`)

| Proveedor | TCP | Entrega | Lag mediano | Reconexión |
|---|---:|---:|---:|---|
| `earthscope_colombia` | 0.16 s | 1 de 2 estaciones | 6.12 s | recuperó con 3.75 s de lag |
| `geofon_chile` | 0.25 s | 1 de 2 estaciones | 1.24 s | no aplicada |

Dos observaciones que el Product Owner y el asesor deben conocer: el primer
paquete tardó entre 39 y 45 s tras conectar, y dos de las cuatro estaciones
probadas no entregaron nada dentro de la ventana de 45 s. Es una medición
puntual, no un acuerdo de disponibilidad.

### Simulacros (`data/drills/`)

| Ensayo | Fuente | Alerta crítica | Actualización oficial |
|---|---|---|---|
| `sa2-drill-simulation-2026-08-30` | evento simulado `bogota` | cerca, umbral-alto | cerca, silenciado |
| `sa2-drill-co-2026-08-10-m7.4` | onda real M7.4 | cerca, umbral-alto | — |
| `sa2-drill-co-2023-08-17-m6.1` | onda real M6.1 | cerca, umbral-alto | — |
| `sa2-drill-co-2023-08-27-m5.7` | onda real M5.7 | cerca, umbral-alto | — |
| `sa2-drill-ambient-noise` | ruido ambiental | ninguna | — |

Cada ensayo recorrió HTTP real, firma HMAC, Redis Streams, dispatcher y consulta
de la bitácora offline. El dispositivo fuera del radio elegido no aparece en
ningún ensayo, y el caso de ruido ambiental produjo disparos locales de hasta
16.3 de razón STA/LTA en `CM.PRA` que la coincidencia multiestación descartó sin
alertar. Latencias de ingesta entre 12 y 65 ms y de despacho entre 10 y 17 ms,
medidas en una sola máquina y sin red intermedia.

`tests/test_drill_evidence.py` vuelve a comprobar estas afirmaciones en cada
ejecución de la suite, de modo que un cambio en la política que las invalide
rompa las pruebas en lugar de dejar el documento desactualizado.

## Limitaciones registradas

1. El APK de release se firmó con la clave de depuración mediante
   `-PseismikUnsignedReleaseCheck=true` para verificar la compilación. La
   distribución firmada se produce con `tools/build-signed-release.ps1`, que sólo
   puede ejecutar la cuenta de Windows dueña del blob DPAPI de la contraseña.
2. iOS no se compiló en esta máquina: requiere macOS con Xcode. La verificación
   quedó delegada al job `ios` de CI (`macos-latest`, `--no-codesign`) y a
   `tests/test_ios_configuration.py`. Firmar y probar en un iPhone real sigue
   pendiente.
3. El push permanece en `dry_run`; ninguna notificación real salió de este
   entorno, y las pruebas lo verifican en toda la evidencia de simulacros.
4. Los simulacros usan `fakeredis` en lugar de Redis: no miden durabilidad,
   reentrega tras caída ni comportamiento de los grupos de consumidores bajo
   carga. Eso exige el entorno con Docker o la VM.
5. La medición SeedLink es puntual y de dos proveedores; no caracteriza
   disponibilidad sostenida, pérdida por zona ni la tasa de falsos disparos.
6. La calibración sismológica formal de umbrales sigue siendo responsabilidad
   del asesor científico y no forma parte de esta entrega.

## Próxima puerta de control

1. Compilar y firmar la beta iOS en macOS y verificar Critical Alerts en un
   iPhone real del equipo de prueba; el job `ios` de CI ya cubre la compilación.
2. Ejecutar `tools/build-signed-release.ps1` en la estación con el keystore y
   registrar el SHA-256 del artefacto y la huella del certificado firmante.
3. Ejecutar el shadow run con estaciones reales y registrar latencia, pérdida y
   falsos disparos por zona.
4. Ejecutar el simulacro cerrado en Android e iOS con la allowlist de testers y
   `tools/simulate_event.py`, y registrar la evidencia.
5. Someter el perfil de alertamiento a revisión del asesor científico antes de
   cualquier decisión sobre activación pública.

No se habilitan alertas públicas certificadas ni cobros en este Sprint.
