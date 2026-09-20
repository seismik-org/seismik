import 'dart:convert';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'event.dart';

/// Cliente mínimo del reloj.
///
/// El reloj se registra como un dispositivo más y consulta el historial con su
/// propia sesión, igual que la beta de Android. No recibe avisos por su cuenta:
/// las alertas llegan reflejadas del teléfono emparejado.
class SeismikWearApi {
  SeismikWearApi({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      baseUrl = baseUrl ?? defaultBaseUrl;

  static const String defaultBaseUrl = 'https://api.seismik.org';

  /// Si App Check no responde, se manda esta marca: el servidor la acepta
  /// sólo mientras la verificación no esté exigida. Hoy sí lo está, así que
  /// un reloj sin App Check recibe un 401 y la app lo dice con claridad.
  static const String unverifiedMarker = 'seismik-beta-wear-unverified';

  /// Token de integridad del reloj. El paquete y la firma son los mismos de la
  /// app de teléfono, así que Firebase lo reconoce como la misma aplicación.
  Future<String> _integrityToken() async {
    try {
      final String? token = await FirebaseAppCheck.instance.getToken();
      if (token != null && token.length >= 16) return token;
    } on Object {
      // Un reloj sin Play Services utilizable no puede atestiguar nada.
    }
    return unverifiedMarker;
  }

  static const String _deviceIdKey = 'wear.device_id';
  static const String _sessionKey = 'wear.device_session';
  static const String _cacheKey = 'wear.events';

  final http.Client _client;
  final String baseUrl;

  Future<String> _deviceId() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? saved = preferences.getString(_deviceIdKey);
    if (saved != null && saved.length >= 8) return saved;
    // Sin dependencias extra: la hora y un contador bastan para un
    // identificador estable, que además se guarda una sola vez.
    final String created =
        'wear-${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
    await preferences.setString(_deviceIdKey, created);
    return created;
  }

  Future<String?> _session() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    return preferences.getString(_sessionKey);
  }

  /// Registra el reloj y devuelve la sesión con la que consultar la API.
  Future<String> register({double? latitude, double? longitude}) async {
    final String deviceId = await _deviceId();
    final http.Response response = await _client
        .post(
          Uri.parse('$baseUrl/v1/devices/register'),
          headers: <String, String>{'Content-Type': 'application/json'},
          body: jsonEncode(<String, dynamic>{
            'device_id': deviceId,
            'platform': 'android',
            'play_integrity_token': await _integrityToken(),
            'locale': 'es',
            'latitude': ?latitude,
            'longitude': ?longitude,
            // El reloj no muestra alarmas propias: sólo consulta.
            'receive_early_alerts': false,
            'receive_official_updates': false,
          }),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode == 401) {
      throw const SeismikWearException(
        'El reloj no pudo verificarse con Google Play. Instala la app desde '
        'el mismo origen que la del teléfono.',
      );
    }
    if (response.statusCode >= 400) {
      throw SeismikWearException(
        'El servidor rechazó el registro del reloj (${response.statusCode}).',
      );
    }
    final Map<String, dynamic> payload =
        jsonDecode(response.body) as Map<String, dynamic>;
    final String session = '${payload['device_session_token']}';
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_sessionKey, session);
    return session;
  }

  /// Últimos sismos. Si el servidor falla, lanza: quien llama decide si
  /// muestra lo guardado, para no hacer pasar lo viejo por nuevo.
  Future<List<WearEvent>> recentEvents({int days = 3, int limit = 20}) async {
    String? session = await _session();
    session ??= await register();

    Future<http.Response> ask(String token) => _client
        .get(
          Uri.parse(
            '$baseUrl/v1/events/history'
            '?days=$days&limit=$limit&minimum_magnitude=2.5'
            '&sources=sgc_colombia,usgs_global',
          ),
          headers: <String, String>{'X-Seismik-Device-Session': token},
        )
        .timeout(const Duration(seconds: 20));

    http.Response response = await ask(session);
    if (response.statusCode == 401 || response.statusCode == 403) {
      // La sesión caducó: registrarse otra vez es barato y silencioso.
      response = await ask(await register());
    }
    if (response.statusCode >= 400) {
      throw SeismikWearException(
        'No se pudo consultar el historial (${response.statusCode}).',
      );
    }
    final Map<String, dynamic> payload =
        jsonDecode(response.body) as Map<String, dynamic>;
    final List<WearEvent> events = <WearEvent>[
      for (final Object? item in (payload['events'] as List<Object?>? ?? const <Object?>[]))
        if (item is Map<String, dynamic>) WearEvent.fromMap(item),
    ];
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_cacheKey, jsonEncode(payload['events']));
    return events;
  }

  /// Lo último que se descargó, para tener algo que mostrar sin red.
  Future<List<WearEvent>> cachedEvents() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? raw = preferences.getString(_cacheKey);
    if (raw == null) return <WearEvent>[];
    try {
      final Object? decoded = jsonDecode(raw);
      if (decoded is! List) return <WearEvent>[];
      return <WearEvent>[
        for (final Object? item in decoded)
          if (item is Map<String, dynamic>) WearEvent.fromMap(item),
      ];
    } on FormatException {
      return <WearEvent>[];
    }
  }
}

class SeismikWearException implements Exception {
  const SeismikWearException(this.message);

  final String message;

  @override
  String toString() => message;
}
