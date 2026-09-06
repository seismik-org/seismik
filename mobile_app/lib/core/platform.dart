import 'package:flutter/foundation.dart';

/// Indica si la interfaz debe presentarse con el lenguaje visual de iOS.
///
/// Se apoya en `defaultTargetPlatform` y no en `Platform.isIOS` por dos razones:
/// respeta `debugDefaultTargetPlatformOverride`, de modo que las pruebas de
/// widgets pueden simular un iPhone sin un dispositivo, y no obliga a importar
/// `dart:io` en widgets que sólo necesitan saber en qué plataforma dibujan.
///
/// Android conserva su presentación Material: esta bandera nunca es verdadera
/// allí, así que cada rama Cupertino es aditiva.
bool get usesCupertino =>
    defaultTargetPlatform == TargetPlatform.iOS ||
    defaultTargetPlatform == TargetPlatform.macOS;
