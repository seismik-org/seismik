import 'package:shared_preferences/shared_preferences.dart';

/// Pide una sola vez, en el primer arranque, lo que no tiene un diálogo propio.
///
/// Las notificaciones y la ubicación ya se piden al abrir la app. El acceso a
/// pantalla completa de Android 14+ no: es una página de Ajustes, y sin ella la
/// alarma se degrada a un banner con el teléfono bloqueado. Antes la persona
/// tenía que encontrarla en Configuración; ahora se le lleva de entrada.
///
/// Se marca como hecho **antes** de abrir Ajustes: esa pantalla saca a la
/// persona de la app, y si volviera a abrirse en cada arranque sería un molestia.
/// Si la rechaza, Configuración > Alertas críticas sigue ahí.
class FirstRunPermissions {
  const FirstRunPermissions();

  static const String criticalAccessKey = 'seismik_first_run_critical_access_v1';

  /// Ejecuta [request] la primera vez y nunca más. Devuelve si se ejecutó.
  Future<bool> runOnce(Future<bool> Function() request) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    if (preferences.getBool(criticalAccessKey) ?? false) return false;
    await preferences.setBool(criticalAccessKey, true);
    await request();
    return true;
  }
}
