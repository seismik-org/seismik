import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Puente con el reloj emparejado.
///
/// «Búsqueda de familiares» exige la sesión de la cuenta, y en una pantalla de
/// 4 cm no se inicia sesión. El teléfono la publica por el Data Layer de Wear,
/// que sólo alcanza al reloj vinculado a este teléfono, y la retira al cerrar
/// sesión. Sin reloj emparejado el dato queda en el teléfono sin ir a ninguna
/// parte.
class WearBridge {
  const WearBridge({MethodChannel channel = _defaultChannel})
    : _channel = channel;

  static const MethodChannel _defaultChannel = MethodChannel('seismik/wear');

  final MethodChannel _channel;

  bool get _supported => !kIsWeb && Platform.isAndroid;

  /// Comparte la sesión con el reloj. Un fallo aquí no puede romper el inicio
  /// de sesión del teléfono: el reloj es un extra.
  Future<void> publishAccount({required String session, String? name}) async {
    if (!_supported) return;
    try {
      await _channel.invokeMethod<bool>('publishAccount', <String, String?>{
        'session': session,
        'name': name,
      });
    } on PlatformException catch (error) {
      debugPrint('No se pudo compartir la sesión con el reloj: ${error.code}');
    } on MissingPluginException {
      // Una compilación sin la parte nativa: el teléfono sigue funcionando.
    }
  }

  /// Retira la sesión del reloj al cerrar sesión en el teléfono.
  Future<void> clearAccount() async {
    if (!_supported) return;
    try {
      await _channel.invokeMethod<bool>('clearAccount');
    } on PlatformException catch (error) {
      debugPrint('No se pudo retirar la sesión del reloj: ${error.code}');
    } on MissingPluginException {
      // Sin parte nativa no hay nada que retirar.
    }
  }
}
