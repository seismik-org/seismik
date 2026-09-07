# Qué falta probar en un iPhone real

Build de referencia: **1.0.0 (29)**.

## Qué corre realmente en el iPhone

Desde el commit `ac1c1d5`, la app de iPhone es **nativa en Swift y SwiftUI con
MapKit**. `AppDelegate` y `SceneDelegate` sustituyen la vista raíz por
`UIHostingController(rootView: SeismikNativeAppRoot())`, así que **el motor
Flutter no dibuja nada en iOS**: todo el código Dart queda inerte en ese
dispositivo aunque siga empaquetado en el binario.

Android sigue usando la app Flutter. Son dos implementaciones independientes del
mismo producto, y esa es la primera cosa que hay que tener presente al probar:
**verificar una no dice nada sobre la otra**.

## Lo que ya está verificado sin iPhone

| Comprobación | Cómo | Qué cubre |
|---|---|---|
| El proyecto Xcode compila, incluido todo el Swift nativo | Job `ios` de CI en `macos-latest` | Sintaxis y enlazado, no comportamiento |
| `Info.plist` y entitlements bien formados | `pytest tests/test_ios_configuration.py` | Configuración |
| El proyecto copia `GoogleService-Info.plist` como recurso | `pytest tests/test_ios_configuration.py` | Configuración |
| Backend completo | `pytest`, `ruff`, `mypy` | API, política de alertas, simulacros |
| App **Android** | `flutter analyze`, `flutter test` (66 pruebas) | Sólo Android |
| Lógica **iPhone**: cola offline y acelerómetro | `xcodebuild test` en CI | Sólo lógica, no interfaz |

El código Swift ya tiene pruebas propias: `ios/RunnerTests/SeismikNativeTests.swift`
cubre la cola offline (persistencia, deduplicación, corte ante fallo de red,
rechazo definitivo, vencimiento) y el disparo del acelerómetro. CI las ejecuta en
un simulador con `xcodebuild test`. Lo que sigue depende de un dispositivo real
porque push, APNs, MapKit y el rendimiento del material no existen en CI.

## Paridad con la app Android

Las funciones que faltaban en el cliente nativo ya están portadas. La tabla
recoge cómo lo hace cada plataforma, porque el comportamiento es el mismo pero
la implementación no:

| Función | Android (Flutter) | iPhone (Swift) |
|---|---|---|
| Cola de reportes sin conexión | `OfflineReportQueue` en `SharedPreferences` | `OfflineReportQueue` en `UserDefaults` |
| Recuperar alertas perdidas | `GET /v1/alerts/recent` con cursor | Igual, mismo cursor |
| Detección colaborativa | `sensors_plus` + `battery_plus` | CoreMotion + `UIDevice` |
| Umbral del acelerómetro | 0.04 g, ventana 2.5 s, varianza 0.12 | Idénticos (`SeismikDSP`) |
| Firma de reportes | HMAC-SHA256 sobre el cuerpo | Igual, con `CryptoKit` |
| Caché del historial | `SharedPreferences` | `UserDefaults` |
| Push | FCM | APNs directo |

Tres detalles que conviene tener presentes al probar:

- La cola guarda el **cuerpo ya codificado**, no el modelo. La firma HMAC cubre
  esos bytes exactos, así que recodificar al reintentar podría cambiar el orden
  de las claves y producir una firma que el servidor rechaza.
- El `report_id` y la hora de observación no cambian entre intentos: el servidor
  reconoce el reenvío como el mismo reporte, no como uno nuevo.
- Cambiar la magnitud mínima o el radio vuelve a registrar el dispositivo. Esos
  filtros los evalúa el despachador, no la app.

### Sigue pendiente

- **Integridad del dispositivo**: `app_attest_token` es todavía la cadena fija
  `seismik-beta-sideload-unverified`. Con `integrity_verification_enabled`
  activo en producción, el alta será rechazada.

## Bloque 1 — Arranque y registro del dispositivo

1. Instala la build desde TestFlight en un iPhone con iOS 15 o superior.
2. Acepta el permiso de notificaciones y el de ubicación **mientras se usa**.
3. Confirma que la app abre el mapa nativo (MapKit) sin pantalla en blanco.
4. En Configuración, comprueba que aparece el identificador del dispositivo.

**Qué mirar aquí en esta arquitectura:** el registro ya no depende de Firebase.
`AppDelegate` llama a `registerForRemoteNotifications()` y guarda el token APNs
en hexadecimal; sólo entonces `SeismikState.updateRegistration()` envía el alta.
Si el registro nunca ocurre, el sospechoso es el permiso de notificaciones o el
entitlement `aps-environment`, no `GoogleService-Info.plist`.

Evidencia a registrar: captura de Configuración y confirmación en el backend de
que el dispositivo aparece como `platform: ios` con `apns_token`.

## Bloque 2 — Alertas

5. Envía un aviso de prueba y confirma que llega con la app en primer plano.
6. Repite con la app en segundo plano.
7. Repite con el iPhone bloqueado.
8. Ejecuta un simulacro dirigido a la allowlist y mide los segundos entre envío
   y llegada.

**Límite conocido:** el entitlement `critical-alerts` sigue sin aprobación de
Apple, así que la build usa `Runner.basic.entitlements`. Con el iPhone en
silencio o No Molestar la alerta llegará como notificación normal. No declares
«alerta crítica funcionando» hasta que Apple apruebe el entitlement.

## Bloque 3 — Interfaz nativa

9. **Pestañas**: las cuatro cambian y la barra usa el material del sistema.
10. **Historial**: el mapa de MapKit se desplaza y amplía; la cabecera flotante
    responde; la hoja inferior arrastra entre sus posiciones sin bloquear el
    mapa.
11. **Liquid Glass**: comprueba el material sobre el mapa en movimiento y en
    modo oscuro. Es el punto de mayor riesgo de rendimiento en iPhone antiguos.
12. **Detalle del sismo**: se abre y vuelve con los gestos del sistema.
13. **Reportes**: envía «Sismo sentido» y «Daños» y confirma que el backend los
    recibe firmados (HMAC con el token crowd).
14. **Abrir epicentro**: verifica el selector de proveedor cartográfico.
15. Dynamic Island / notch, área segura inferior y tamaño de letra grande.

## Bloque 4 — Sin conexión

16. Activa modo avión y abre el historial: debe mostrar la caché local.
17. Con modo avión, **envía un reporte**. Debe aparecer «Sin conexión: el
    reporte quedó guardado en el iPhone». Restaura la red y confirma que se
    envía solo y que el contador de pendientes vuelve a cero.
18. Con la app cerrada durante un simulacro, ábrela después: la alerta perdida
    debe aparecer en el historial una sola vez, aunque abras y cierres varias
    veces.

## Bloque 5 — Android

19. Repite los bloques 1, 2 y 4 en un Android. La app Flutter no cambió de
    arquitectura, pero es la única forma de confirmar que sigue intacta.

## Qué no se puede cerrar en este ciclo

- **Alertas críticas de Apple**: dependen de una aprobación externa.
- **Interfaz y rendimiento en iPhone**: las pruebas cubren la lógica, no cómo
  se ve ni cuánto cuesta dibujarlo.
- **Integridad en producción**: el token de App Attest sigue siendo un marcador
  fijo; hay que emitir uno real antes de activar la verificación.
