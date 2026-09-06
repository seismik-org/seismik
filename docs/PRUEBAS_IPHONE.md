# Qué falta probar en un iPhone real

Build de referencia: **1.0.0 (23)**. La 22 quedó superada por los cambios de
interfaz de este ciclo; sube la 23 antes de repetir el recorrido.

Todo lo que aparece aquí necesita un iPhone físico. Ni el simulador ni CI pueden
cubrirlo: las notificaciones push, el token APNs, App Attest, los mapas nativos y
el rendimiento del desenfoque sólo existen en hardware real.

## Lo que ya está verificado sin iPhone

| Comprobación | Cómo |
|---|---|
| Compilación iOS completa (proyecto Xcode, Pods, AOT de Dart) | Job `ios` de CI en `macos-latest` |
| `Info.plist` y entitlements bien formados y con las claves necesarias | `pytest tests/test_ios_configuration.py` |
| El proyecto copia `GoogleService-Info.plist` como recurso | `pytest tests/test_ios_configuration.py` |
| El workflow de TestFlight inyecta el plist real desde el secreto | `pytest tests/test_ios_configuration.py` |
| Bifurcación Cupertino/Material sin regresión en Android | `flutter test test/adaptive_platform_test.dart` |
| Material de vidrio: desenfoque, squircle, tinte por brillo | `flutter test test/liquid_glass_test.dart` |
| Análisis estático y suite completa | `flutter analyze`, `flutter test` (66 pruebas) |

## Bloque 1 — Arranque y registro del dispositivo

1. Instala la build desde TestFlight en un iPhone con iOS 15 o superior.
2. Acepta el permiso de notificaciones y el de ubicación **mientras se usa**.
3. Confirma que la app llega al mapa sin pantalla en blanco ni cierre.
4. En Configuración → «Identificador de este dispositivo», comprueba que existe
   un identificador.

**Qué puede fallar y no se ve en CI:** si Firebase no quedó configurado, el token
APNs nunca llega y el registro lanza «Push token is not available yet». Ese es el
síntoma exacto de un `GoogleService-Info.plist` ausente o de otro proyecto.

Evidencia a registrar: captura de la pantalla de Configuración y confirmación en
el backend de que el dispositivo aparece registrado como `platform: ios`.

## Bloque 2 — Alertas

5. Configuración → «Probar alerta»: debe sonar y mostrarse la pantalla roja de
   alerta con el contador de segundos.
6. Con la app en segundo plano, repite la prueba y confirma que la notificación
   llega igual.
7. Con el iPhone **bloqueado**, confirma que la alerta aparece en la pantalla de
   bloqueo.
8. Ejecuta un simulacro dirigido a la allowlist
   (`tools/simulate_event.py`, o el workflow con push en modo `testers`) y mide
   cuántos segundos pasan entre el envío y la llegada.

**Límite conocido:** el entitlement `critical-alerts` sigue sin aprobación de
Apple, así que la build usa `Runner.basic.entitlements`. Sin él, iOS respeta el
modo silencio y No Molestar: la alerta llegará como notificación normal. No
declares «alerta crítica funcionando» hasta que Apple apruebe el entitlement y
el perfil de aprovisionamiento lo incluya.

## Bloque 3 — Interfaz de iPhone (lo nuevo de esta build)

9. **Pestañas**: las cuatro pestañas cambian y el mapa se difumina bajo la barra
   en lugar de cortarse contra una franja opaca.
10. **Historial**: la cabecera de vidrio flota sobre el mapa; el botón de
    recargar responde; la hoja inferior arrastra entre sus tres posiciones y el
    mapa sigue moviéndose y ampliándose con la hoja abierta.
11. **Vidrio**: comprueba que el desenfoque se ve sobre el mapa en movimiento y
    que no aparece tirón al arrastrar la hoja. Repite en modo oscuro. Éste es el
    punto con más riesgo de rendimiento en iPhone antiguos.
12. **Detalle del sismo**: se abre empujando desde la derecha y **vuelve
    arrastrando desde el borde izquierdo**; los botones son Cupertino.
13. **Reportes**: en «Sismo sentido» y «Daños», las casillas son interruptores y
    el deslizador de intensidad es el de iOS. Envía un formulario con el código
    de país vacío y confirma que aparece una **alerta nativa**, no un banner
    inferior.
14. **Abrir epicentro**: con el proveedor «Apple Maps» abre Mapas; con «Google
    Maps» abre la app de Google si está instalada; sin ella, el respaldo web.
15. Comprueba Dynamic Island / notch y el área segura inferior en un iPhone con
    ambos, y el texto con tamaño de letra grande en Accesibilidad.

## Bloque 4 — Sin conexión

16. Activa modo avión, envía un reporte y confirma el mensaje «guardado en el
    teléfono».
17. Restaura la red y confirma que el reporte se envía solo y que el contador de
    pendientes vuelve a cero.
18. Con la app cerrada durante un simulacro, ábrela después y confirma que la
    alerta perdida aparece en el historial.

## Bloque 5 — Paridad con Android

19. Repite los bloques 1, 2 y 4 en un Android para confirmar que nada de lo
    anterior cambió allí. La suite automatizada ya cubre que los widgets
    Material siguen en su sitio, pero el comportamiento de push y ubicación
    necesita el dispositivo.

## Qué no se puede cerrar en este ciclo

- **Alertas críticas de Apple**: dependen de una aprobación externa.
- **Rendimiento del vidrio en iPhone antiguos**: sin un dispositivo no hay dato.
  Si aparece tirón, la primera palanca es bajar `blurSigma` en la hoja del
  historial, y la segunda, retirar el vidrio de la cabecera flotante.
- **Latencia real de push**: sólo se mide con dispositivos reales en el
  simulacro cerrado.
