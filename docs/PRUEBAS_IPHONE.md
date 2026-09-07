# Qué falta probar en un iPhone real

Build de referencia: **1.0.0 (28)**.

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

**No hay ninguna prueba automatizada del código Swift.** `ios/RunnerTests` sigue
siendo el archivo plantilla de 12 líneas. Que CI esté en verde significa que el
Swift compila, nada más: ni una sola línea de la app de iPhone está ejercitada.
Por eso todo lo que sigue depende de un dispositivo.

## Diferencias conocidas frente a la app Android

Estas no son fallos por descubrir: son huecos verificados al leer el código
nativo. Convienen anotarse antes de probar para no reportarlos como sorpresas.

| Función | Android (Flutter) | iPhone (Swift) |
|---|---|---|
| Cola de reportes sin conexión | Persiste y reenvía con el mismo `report_id` | **No existe**: un reporte sin red se pierde |
| Recuperar alertas perdidas (`/v1/alerts/recent`) | Sí | **No existe** |
| Detección colaborativa por acelerómetro | Sí | **No existe** |
| Caché del historial para leer sin red | Sí | Sí (`UserDefaults`) |
| Integridad del dispositivo | App Check real | Cadena fija `seismik-beta-sideload-unverified` |
| Push | FCM | APNs directo; `FirebaseApp.configure()` no se llama |

Sobre las dos últimas filas: el backend acepta `apns_token`, así que el push
directo es viable, pero con `integrity_verification_enabled` activo en
producción un token de integridad fijo será rechazado en el registro.

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
17. Con modo avión, **envía un reporte**. Documenta exactamente qué ocurre. Hoy
    no hay cola de reenvío en iOS, así que lo esperable es un error y la pérdida
    del reporte. Si el producto exige la paridad con Android, esto es trabajo
    pendiente, no un defecto de esta build.
18. Con la app cerrada durante un simulacro, ábrela después: en iOS **no** se
    recuperan las alertas perdidas.

## Bloque 5 — Android

19. Repite los bloques 1, 2 y 4 en un Android. La app Flutter no cambió de
    arquitectura, pero es la única forma de confirmar que sigue intacta.

## Qué no se puede cerrar en este ciclo

- **Alertas críticas de Apple**: dependen de una aprobación externa.
- **Comportamiento del código Swift**: sin pruebas automatizadas ni dispositivo,
  no hay ninguna evidencia más allá de que compila.
- **Paridad offline en iPhone**: falta portar la cola de reportes, la
  recuperación de alertas y el crowdsourcing.
- **Integridad en producción**: el token de App Attest es un marcador fijo.
