# Registro Firebase y relojes — 12 de octubre de 2026

## Diagnóstico y corrección del teléfono (build 66)

La captura Android dice `[core/no-app]`: el SDK Dart intentó obtener la app
Firebase predeterminada antes de disponer de ella. La señal de radio no prueba
inicialización Firebase ni acceso a Internet. No hay dispositivo conectado para
atribuir el fallo observado a un APK concreto; el usuario refiere el último
build de Claude. La configuración firmada de ese binario aún debe comprobarse.

El registro ahora espera una puerta compartida de inicialización Firebase y
activación App Check. Los arranques concurrentes se agrupan, los fallos permiten
reintentar y las notificaciones se reenganchan sin duplicar un arranque exitoso.
No se rebaja Play Integrity ni se desactiva App Check. Los builds Android
firmados de teléfono/reloj sin `google-services.json` fallan antes de compilar.

iOS nativo ya configuraba Firebase en AppDelegate. Ahora la preparación común
también se exige al pedir App Check, con exclusión del anfitrión XCTest y error
explícito cuando falta el plist. No afirmar que el fallo nativo de iOS tiene
exactamente la causa de la captura Dart sin versión/logs del dispositivo.

## Wear OS (10002)

Mismo paquete `com.seismik.app`, firma y ficha de Seismik. Canal de colores
propio del reloj: roles de Wear Material 3 y respeto de la opción del sistema
`dynamic_color_theme_enabled`. Sin soporte o con tema desactivado, respaldo
oscuro Seismik; negro OLED, controles redondos, corona, Familia y tile existentes.
Los colores de magnitud/estado son semánticos y no se sustituyen por el tema.
No se añaden alarmas independientes al reloj.

Referencias: [roles AndroidX Wear M3](https://android.googlesource.com/platform/frameworks/support/+/1cc9aac0b446c12d490e06dadf04ec0b1c8ca058/wear/compose/compose-material3/src/main/java/androidx/wear/compose/material3/DynamicColorScheme.kt)
y [diseño Wear](https://developer.android.com/design/ui/wear/guides/styles/color/system).

## Apple Watch — viable, aún no implementado

Conviene un target watchOS SwiftUI acompañante del iPhone, no portar Flutter.
Primera fase: último sismo, intensidad, antigüedad/copia guardada y apertura en
iPhone. WatchConnectivity puede transferir datos y mensajes; no garantiza una
entrega inmediata ni conectividad permanente. Segunda fase: Familia, con
sesión y consentimiento cuidadosamente transferidos. No copiar claves maestras
al reloj ni convertir un pendiente en confirmación de seguridad.

Requiere target/bundle ID y firma adicionales, iconos/capturas, compilación
macOS/Xcode, prueba en reloj físico y distribución de la app acompañante con el
iPhone. La aprobación Critical Alerts para `com.seismik.app` no debe interpretarse
como autorización automática de alarmas propias en un nuevo target watchOS.
No es una red de detección de terremotos con acelerómetro habilitada en segundo
plano; tal función exigiría investigación y pruebas separadas de batería/ruido.

Fuentes: [WatchConnectivity](https://developer.apple.com/documentation/watchconnectivity/transferring-data-with-watch-connectivity)
y [apps watchOS independientes](https://developer.apple.com/documentation/watchos-apps/creating-independent-watchos-apps).
