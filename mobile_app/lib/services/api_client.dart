import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../core/constants.dart';
import '../core/security.dart';
import '../data/models/citizen_report.dart';
import '../data/models/family_circle.dart';
import '../data/models/pending_report.dart';
import '../data/models/seismik_account.dart';
import '../data/models/seismic_event.dart';
import '../data/models/station.dart';

class SeismikApiException implements Exception {
  const SeismikApiException(this.message, this.statusCode);
  final String message;
  final int? statusCode;

  /// El servidor rechazó el contenido: reintentarlo repetiría el mismo error.
  /// 408 y 429 sí son transitorios y vuelven a la cola.
  bool get isPermanent {
    final int? code = statusCode;
    if (code == null) return false;
    return code >= 400 && code < 500 && code != 408 && code != 429;
  }

  /// La sesión de la cuenta falta o venció: hay que volver a iniciar sesión.
  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => 'SeismikApiException($statusCode): $message';
}

class ApiClient {
  ApiClient({http.Client? httpClient})
    : _http = httpClient ?? _persistentHttpClient();

  /// Un único cliente con conexiones persistentes. Cada petición reutiliza el
  /// TLS ya negociado con Cloudflare en vez de repetir el apretón de manos,
  /// que desde una red móvil cuesta cientos de milisegundos por llamada.
  static http.Client _persistentHttpClient() => IOClient(
    HttpClient()
      ..connectionTimeout = const Duration(seconds: 6)
      ..idleTimeout = const Duration(seconds: 45),
  );

  static const String _deviceIdKey = 'seismik.device_id';
  static const String _crowdTokenKey = 'seismik.crowd_token';
  static const String _deviceSessionKey = 'seismik.device_session';
  static const String _eventCacheKey = 'seismik.official_event_cache';
  static const String _alertCursorKey = 'seismik.alert_cursor';
  static const String _stationsCacheKey = 'seismik.stations_cache';
  static const String _stationsCachedAtKey = 'seismik.stations_cached_at';
  static const String _accountSessionKey = 'seismik.account_session';
  static const String _accountProfileKey = 'seismik.account_profile';

  /// Identificadores de sismo que acepta el aviso familiar.
  static final RegExp _eventIdPattern = RegExp(r'^[A-Za-z0-9._:-]{1,128}$');

  /// El catálogo de estaciones cambia muy poco: basta renovarlo dos veces al día.
  static const Duration stationsCacheTtl = Duration(hours: 12);

  /// Por debajo de este tamaño, arrancar un isolate cuesta más que decodificar.
  static const int backgroundParseThreshold = 32 * 1024;

  final http.Client _http;
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();

  // El almacén seguro de Android descifra en cada lectura: la sesión se lee
  // una vez y se conserva en memoria en vez de pagarlo en cada petición.
  String? _sessionToken;
  List<SeismicStation>? _stationsMemory;
  DateTime? _stationsFetchedAt;
  String? _eventsCacheSignature;
  String? _accountToken;

  /// Toda apertura salvo la primera ya tiene sesión: con ella los datos se
  /// pueden pedir sin esperar a que termine un registro nuevo.
  Future<bool> hasDeviceSession() async {
    final String? session = await _deviceSession();
    return session != null && session.isNotEmpty;
  }

  Future<String?> _deviceSession() async =>
      _sessionToken ??= await _secureStorage.read(key: _deviceSessionKey);

  Future<String> ensureDeviceId() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? existing = preferences.getString(_deviceIdKey);
    if (existing != null) return existing;
    final String generated = const Uuid().v4();
    await preferences.setString(_deviceIdKey, generated);
    return generated;
  }

  Future<void> registerDevice({
    required double latitude,
    required double longitude,
    String? zoneId,
    bool receiveEarlyAlerts = true,
    bool receiveOfficialUpdates = true,
    double minimumNotificationMagnitude = 4.0,
    double alertRadiusKm = 250.0,
  }) async {
    final String deviceId = await ensureDeviceId();
    String? integrityToken;
    try {
      // Sin forzar: el SDK devuelve el token vigente (dura cerca de una hora)
      // y sólo pide otro al vencer. Forzarlo exigía una verificación nueva de
      // Play Integrity en cada registro, lenta y con cuota diaria. El servidor
      // lo valida sin consumirlo, así que reutilizarlo es seguro.
      integrityToken = await FirebaseAppCheck.instance.getToken();
    } catch (_) {
      if (SeismikConstants.integrityRequired) rethrow;
    }
    if (integrityToken == null && SeismikConstants.integrityRequired) {
      throw const SeismikApiException('App Check did not return a token', null);
    }
    // La beta distribuida fuera de Play Store no siempre obtiene un veredicto
    // Play Integrity. El backend beta no verifica este marcador; producción
    // compila con SEISMIK_INTEGRITY_REQUIRED=true y nunca usa este fallback.
    integrityToken ??= 'seismik-beta-sideload-unverified';
    final FirebaseMessaging messaging = FirebaseMessaging.instance;
    final String? pushToken = Platform.isIOS
        ? await messaging.getAPNSToken()
        : await messaging.getToken();
    if (pushToken == null) {
      throw const SeismikApiException('Push token is not available yet', null);
    }
    final NotificationSettings permission = await messaging
        .getNotificationSettings();
    final Map<String, dynamic> payload = <String, dynamic>{
      'device_id': deviceId,
      'platform': Platform.isIOS ? 'ios' : 'android',
      'apns_token': Platform.isIOS ? pushToken : null,
      'fcm_token': Platform.isAndroid ? pushToken : null,
      'zone_id': zoneId,
      'latitude': latitude,
      'longitude': longitude,
      'critical_alerts_authorized': Platform.isIOS
          ? permission.criticalAlert == AppleNotificationSetting.enabled
          : permission.authorizationStatus == AuthorizationStatus.authorized,
      'receive_early_alerts': receiveEarlyAlerts,
      'receive_official_updates': receiveOfficialUpdates,
      'minimum_notification_magnitude': minimumNotificationMagnitude,
      'alert_radius_km': alertRadiusKm,
      'locale': Platform.localeName,
      'country_code': _localeCountryCode(),
      'app_attest_token': Platform.isIOS ? integrityToken : null,
      'play_integrity_token': Platform.isAndroid ? integrityToken : null,
    };
    final http.Response response = await _http
        .post(
          _uri('/v1/devices/register'),
          headers: _jsonHeaders(),
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 8));
    final Map<String, dynamic> decoded = _decode(response);
    final String? crowdToken = decoded['crowd_token']?.toString();
    final String? deviceSession = decoded['device_session_token']?.toString();
    if (crowdToken == null || crowdToken.isEmpty || deviceSession == null || deviceSession.isEmpty) {
      throw SeismikApiException(
        'Registration omitted device credentials',
        response.statusCode,
      );
    }
    await _secureStorage.write(key: _crowdTokenKey, value: crowdToken);
    await _secureStorage.write(key: _deviceSessionKey, value: deviceSession);
    _sessionToken = deviceSession;
  }

  Future<void> sendShake({
    required double latitude,
    required double longitude,
    required double pgaG,
    required int timestampMilliseconds,
  }) async {
    final String? token = await _crowdToken();
    if (token == null) {
      throw const SeismikApiException('Device is not registered', null);
    }
    final String deviceId = await ensureDeviceId();
    final String body = jsonEncode(<String, dynamic>{
      'device_id': deviceId,
      'lat': latitude,
      'lon': longitude,
      'pga': pgaG,
      'timestamp': timestampMilliseconds,
    });
    final List<int> bodyBytes = utf8.encode(body);
    final String timestamp = (timestampMilliseconds / 1000).toStringAsFixed(3);
    final String signature = SeismikSecurity.hmacSha256Hex(
      secret: token,
      timestamp: timestamp,
      bodyBytes: bodyBytes,
    );
    final http.Response response = await _http
        .post(
          _uri('/v1/crowd/shake'),
          headers: <String, String>{
            ..._jsonHeaders(),
            'X-Seismik-Timestamp': timestamp,
            'X-Seismik-Signature': signature,
          },
          body: body,
        )
        .timeout(const Duration(seconds: 3));
    _decode(response);
  }

  /// Compone el cuerpo del reporte sin enviarlo.
  ///
  /// La app necesita el cuerpo listo antes de saber si hay red: si el envío
  /// falla, ese mismo cuerpo se guarda en la cola offline y se reintenta sin
  /// cambiar `report_id` ni `observed_at`.
  Future<Map<String, dynamic>> buildFeltReport({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
    required Set<String> selectedAgencyIds,
    required bool felt,
    required int? intensityMmi,
    required String? earthquakeEventId,
    required String? officialEventId,
    bool? indoors,
    int? floor,
    bool? wokeUp,
    bool? difficultyStanding,
    bool? objectsMoved,
    bool? objectsFell,
    bool? visibleDamage,
    String? comment,
  }) async =>
      await _reportBase(
        latitude: latitude,
        longitude: longitude,
        countryCode: countryCode,
        preciseLocation: preciseLocation,
        shareWithOfficialAgencies: shareWithOfficialAgencies,
        selectedAgencyIds: selectedAgencyIds,
        earthquakeEventId: earthquakeEventId,
        officialEventId: officialEventId,
        comment: comment,
      )..addAll(<String, dynamic>{
        'type': 'seismik_felt_report',
        'felt': felt,
        'intensity_mmi': felt ? intensityMmi : null,
        'indoors': indoors,
        'floor': floor,
        'woke_up': wokeUp,
        'difficulty_standing': difficultyStanding,
        'objects_moved': objectsMoved,
        'objects_fell': objectsFell,
        'visible_damage': visibleDamage,
      });

  Future<Map<String, dynamic>> buildDamageReport({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
    required String severity,
    required List<String> hazards,
    required bool peopleTrapped,
    required bool injuriesObserved,
    required bool emergencyServicesContacted,
    required bool? safeToRemain,
    required String? earthquakeEventId,
    required String? officialEventId,
    String? buildingType,
    String? comment,
  }) async =>
      await _reportBase(
        latitude: latitude,
        longitude: longitude,
        countryCode: countryCode,
        preciseLocation: preciseLocation,
        shareWithOfficialAgencies: shareWithOfficialAgencies,
        selectedAgencyIds: const <String>{},
        earthquakeEventId: earthquakeEventId,
        officialEventId: officialEventId,
        comment: comment,
      )..addAll(<String, dynamic>{
        'type': 'seismik_damage_report',
        'severity': severity,
        'hazards': hazards,
        'building_type': _nullIfBlank(buildingType),
        'people_trapped': peopleTrapped,
        'injuries_observed': injuriesObserved,
        'emergency_services_contacted': emergencyServicesContacted,
        'safe_to_remain': safeToRemain,
      });

  /// Envía un cuerpo ya compuesto (recién creado o recuperado de la cola).
  Future<ReportResult> sendReport(
    String path,
    Map<String, dynamic> payload,
  ) async => ReportResult.fromMap(await _postSigned(path, payload));

  Future<ReportResult> submitFeltReport({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
    required Set<String> selectedAgencyIds,
    required bool felt,
    required int? intensityMmi,
    required String? earthquakeEventId,
    required String? officialEventId,
    bool? indoors,
    int? floor,
    bool? wokeUp,
    bool? difficultyStanding,
    bool? objectsMoved,
    bool? objectsFell,
    bool? visibleDamage,
    String? comment,
  }) async {
    final Map<String, dynamic> payload = await buildFeltReport(
      latitude: latitude,
      longitude: longitude,
      countryCode: countryCode,
      preciseLocation: preciseLocation,
      shareWithOfficialAgencies: shareWithOfficialAgencies,
      selectedAgencyIds: selectedAgencyIds,
      felt: felt,
      intensityMmi: intensityMmi,
      earthquakeEventId: earthquakeEventId,
      officialEventId: officialEventId,
      indoors: indoors,
      floor: floor,
      wokeUp: wokeUp,
      difficultyStanding: difficultyStanding,
      objectsMoved: objectsMoved,
      objectsFell: objectsFell,
      visibleDamage: visibleDamage,
      comment: comment,
    );
    return sendReport(PendingReportKind.felt.path, payload);
  }

  Future<ReportResult> submitDamageReport({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
    required String severity,
    required List<String> hazards,
    required bool peopleTrapped,
    required bool injuriesObserved,
    required bool emergencyServicesContacted,
    required bool? safeToRemain,
    required String? earthquakeEventId,
    required String? officialEventId,
    String? buildingType,
    String? comment,
  }) async {
    final Map<String, dynamic> payload = await buildDamageReport(
      latitude: latitude,
      longitude: longitude,
      countryCode: countryCode,
      preciseLocation: preciseLocation,
      shareWithOfficialAgencies: shareWithOfficialAgencies,
      severity: severity,
      hazards: hazards,
      peopleTrapped: peopleTrapped,
      injuriesObserved: injuriesObserved,
      emergencyServicesContacted: emergencyServicesContacted,
      safeToRemain: safeToRemain,
      earthquakeEventId: earthquakeEventId,
      officialEventId: officialEventId,
      buildingType: buildingType,
      comment: comment,
    );
    return sendReport(PendingReportKind.damage.path, payload);
  }

  Future<Map<String, dynamic>> _reportBase({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
    required Set<String> selectedAgencyIds,
    required String? earthquakeEventId,
    required String? officialEventId,
    required String? comment,
  }) async => <String, dynamic>{
    'report_id': const Uuid().v4(),
    'device_id': await ensureDeviceId(),
    'earthquake_event_id': earthquakeEventId,
    'official_event_id': officialEventId,
    'observed_at': DateTime.now().toUtc().toIso8601String(),
    'latitude': latitude,
    'longitude': longitude,
    'location_accuracy_m': null,
    'location_precision': preciseLocation ? 'precise' : 'approximate',
    'country_code': countryCode.trim().toUpperCase(),
    'share_with_official_agencies': shareWithOfficialAgencies,
    'selected_agency_ids': selectedAgencyIds.toList()..sort(),
    'consent_version': '2026-08',
    'comment': _nullIfBlank(comment),
  };

  Future<Map<String, dynamic>> _postSigned(
    String path,
    Map<String, dynamic> payload,
  ) async {
    final String? token = await _crowdToken();
    if (token == null) {
      throw const SeismikApiException(
        'El dispositivo no está registrado',
        null,
      );
    }
    final String body = jsonEncode(payload);
    final String timestamp = (DateTime.now().millisecondsSinceEpoch / 1000)
        .toStringAsFixed(3);
    final String signature = SeismikSecurity.hmacSha256Hex(
      secret: token,
      timestamp: timestamp,
      bodyBytes: utf8.encode(body),
    );
    final http.Response response = await _http
        .post(
          _uri(path),
          headers: <String, String>{
            ..._jsonHeaders(),
            'X-Seismik-Timestamp': timestamp,
            'X-Seismik-Signature': signature,
          },
          body: body,
        )
        .timeout(const Duration(seconds: 8));
    return _decode(response);
  }

  static String? _nullIfBlank(String? value) {
    final String? trimmed = value?.trim();
    return trimmed == null || trimmed.isEmpty ? null : trimmed;
  }

  static String? _localeCountryCode() {
    final List<String> parts = Platform.localeName.split(RegExp('[-_]'));
    if (parts.length < 2 || parts.last.length != 2) return null;
    return parts.last.toUpperCase();
  }

  /// Catálogo de estaciones sísmicas: cientos de kilobytes, casi siempre igual.
  ///
  /// Se sirve desde memoria o desde el teléfono mientras tenga menos de
  /// [stationsCacheTtl], así abrir la app o volver a ella no lo descarga cada
  /// vez. Mientras no cambie se devuelve la misma lista, lo que permite al mapa
  /// saltarse la reconstrucción de sus marcadores.
  Future<List<SeismicStation>> fetchStations({bool forceRefresh = false}) async {
    final DateTime now = DateTime.now();
    if (!forceRefresh) {
      final List<SeismicStation> known =
          _stationsMemory ?? await readCachedStations();
      final DateTime? fetchedAt = _stationsFetchedAt;
      if (known.isNotEmpty &&
          fetchedAt != null &&
          now.difference(fetchedAt) < stationsCacheTtl) {
        return known;
      }
    }
    try {
      final http.Response response = await _http
          .get(_uri('/v1/network/stations'), headers: await _mobileHeaders())
          .timeout(const Duration(seconds: 10));
      _ensureSuccess(response);
      final List<SeismicStation> stations = await _parseInBackground(
        parseStationsBody,
        response.body,
      );
      _stationsMemory = stations;
      _stationsFetchedAt = now;
      try {
        final SharedPreferences preferences =
            await SharedPreferences.getInstance();
        await preferences.setString(_stationsCacheKey, response.body);
        await preferences.setInt(
          _stationsCachedAtKey,
          now.millisecondsSinceEpoch,
        );
      } catch (_) {
        // Sin caché en disco la app funciona igual; sólo descargará otra vez.
      }
      return stations;
    } catch (_) {
      // Sin red, un catálogo vencido sigue siendo mejor que un mapa vacío.
      final List<SeismicStation>? fallback = _stationsMemory;
      if (fallback != null && fallback.isNotEmpty) return fallback;
      rethrow;
    }
  }

  /// Estaciones guardadas en el teléfono, para dibujar el mapa al instante.
  Future<List<SeismicStation>> readCachedStations() async {
    final List<SeismicStation>? memory = _stationsMemory;
    if (memory != null) return memory;
    try {
      final SharedPreferences preferences =
          await SharedPreferences.getInstance();
      final String? raw = preferences.getString(_stationsCacheKey);
      if (raw == null || raw.isEmpty) return const <SeismicStation>[];
      final List<SeismicStation> stations = await _parseInBackground(
        parseStationsBody,
        raw,
      );
      // Una descarga pudo llenar la memoria mientras se leía el disco.
      final List<SeismicStation>? downloaded = _stationsMemory;
      if (downloaded != null) return downloaded;
      _stationsMemory = stations;
      final int? cachedAt = preferences.getInt(_stationsCachedAtKey);
      _stationsFetchedAt = cachedAt == null
          ? null
          : DateTime.fromMillisecondsSinceEpoch(cachedAt);
      return stations;
    } catch (_) {
      return const <SeismicStation>[];
    }
  }

  Future<List<AgencyRoute>> fetchReportingAgencies({
    required String countryCode,
    String? officialEventId,
  }) async {
    final Uri uri = _uri('/v1/reports/agencies').replace(
      queryParameters: <String, String>{
        'country_code': countryCode.trim().toUpperCase(),
        if (officialEventId != null && officialEventId.isNotEmpty)
          'official_event_id': officialEventId,
      },
    );
    final http.Response response = await _http
        .get(uri, headers: _jsonHeaders())
        .timeout(const Duration(seconds: 8));
    final Object? decoded = response.body.isEmpty
        ? <dynamic>[]
        : jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw SeismikApiException(decoded.toString(), response.statusCode);
    }
    if (decoded is! List<dynamic>) {
      throw SeismikApiException(
        'Unexpected agency catalog response',
        response.statusCode,
      );
    }
    return decoded
        .whereType<Map<String, dynamic>>()
        .map(AgencyRoute.fromMap)
        .toList(growable: false);
  }

  Future<List<SeismicEvent>> fetchRecentEvents({
    Set<String> sourceIds = const <String>{'sgc_colombia', 'usgs_global'},
    int days = 7,
    double minimumMagnitude = 2.5,
  }) async {
    final Uri historyUri = _uri('/v1/events/history').replace(
      queryParameters: <String, String>{
        'sources': (sourceIds.toList()..sort()).join(','),
        'days': days.toString(),
        'minimum_magnitude': minimumMagnitude.toStringAsFixed(1),
        'limit': '200',
      },
    );
    final http.Response response = await _http
        .get(historyUri, headers: await _mobileHeaders())
        .timeout(const Duration(seconds: 12));
    // Sólo un servidor anterior al historial combinado responde 404. Ante otros
    // fallos, repetir contra la ruta antigua sumaba hasta 8 s de espera antes
    // de que la app mostrara lo que ya tenía guardado.
    final List<SeismicEvent> events;
    if (response.statusCode == 404) {
      events = await _fetchLegacyRecentEvents();
    } else {
      _ensureSuccess(response);
      events = await _parseInBackground(parseEventsBody, response.body);
    }
    unawaited(_cacheEvents(events));
    return events;
  }

  /// Recupera las alertas emitidas mientras el teléfono estuvo sin conexión.
  ///
  /// El cursor se guarda en el dispositivo para no volver a mostrar avisos ya
  /// vistos; una respuesta 404 significa que el registro se perdió (por ejemplo,
  /// tras reinstalar) y el próximo registro del dispositivo lo restablece.
  Future<List<SeismicEvent>> fetchMissedAlerts() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String deviceId = await ensureDeviceId();
    final String? cursor = preferences.getString(_alertCursorKey);
    final Uri uri = _uri('/v1/alerts/recent').replace(
      queryParameters: <String, String>{
        'device_id': deviceId,
        if (cursor != null && cursor.isNotEmpty) 'since': cursor,
      },
    );
    final http.Response response = await _http
        .get(uri, headers: await _mobileHeaders())
        .timeout(const Duration(seconds: 8));
    if (response.statusCode == 404) return <SeismicEvent>[];
    final Map<String, dynamic> decoded = _decode(response);
    final String? nextCursor = decoded['cursor']?.toString();
    if (nextCursor != null && nextCursor.isNotEmpty) {
      await preferences.setString(_alertCursorKey, nextCursor);
    }
    return (decoded['alerts'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(
          (alert) => SeismicEvent.fromMap(<String, dynamic>{
            ...alert,
            'detected_at': alert['emitted_at'],
          }),
        )
        .toList(growable: false);
  }

  // ---------------------------------------------------------------------------
  // Cuenta Seismik
  // ---------------------------------------------------------------------------

  /// Cuenta con sesión guardada en este teléfono, o `null`.
  Future<SeismikAccount?> currentAccount() async {
    final String? token = await _accountSession();
    if (token == null || token.isEmpty) return null;
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? raw = preferences.getString(_accountProfileKey);
    if (raw == null) return null;
    final Object? decoded = jsonDecode(raw);
    return decoded is Map<String, dynamic>
        ? SeismikAccount.fromMap(decoded)
        : null;
  }

  /// Canjea el código de un solo uso del retorno por una sesión de cuenta.
  ///
  /// El verificador PKCE prueba que este teléfono empezó el inicio de sesión:
  /// si otra app interceptó `seismik://auth/callback`, el código no le sirve.
  Future<SeismikAccount> exchangeOAuthCode({
    required String code,
    required String verifier,
  }) async {
    final http.Response response = await _http
        .post(
          Uri.parse('${SeismikConstants.authBaseUrl}/v1/oauth/mobile/exchange'),
          headers: _jsonHeaders(),
          body: jsonEncode(<String, String>{
            'code': code,
            'code_verifier': verifier,
          }),
        )
        .timeout(const Duration(seconds: 10));
    final Map<String, dynamic> decoded = _decode(response);
    final String token = decoded['mobile_session_token']?.toString() ?? '';
    if (token.isEmpty) {
      throw SeismikApiException(
        'Sign-in omitted the account session',
        response.statusCode,
      );
    }
    final SeismikAccount account = SeismikAccount.fromMap(decoded);
    await _secureStorage.write(key: _accountSessionKey, value: token);
    _accountToken = token;
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_accountProfileKey, jsonEncode(account.toMap()));
    return account;
  }

  Future<void> clearAccount() async {
    _accountToken = null;
    await _secureStorage.delete(key: _accountSessionKey);
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.remove(_accountProfileKey);
  }

  /// Asocia este teléfono a la cuenta: aquí llegarán los avisos de la familia.
  Future<void> linkDeviceToAccount() async {
    final http.Response response = await _http
        .post(
          _uri('/v1/account/device'),
          headers: await _accountHeaders(requireDevice: true),
        )
        .timeout(const Duration(seconds: 8));
    _decode(response);
  }

  Future<void> unlinkDeviceFromAccount() async {
    final http.Response response = await _http
        .delete(
          _uri('/v1/account/device'),
          headers: await _accountHeaders(requireDevice: true),
        )
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 204) _decode(response);
  }

  // ---------------------------------------------------------------------------
  // Búsqueda de familiares
  // ---------------------------------------------------------------------------

  Future<FamilyCircle?> fetchFamilyCircle() async {
    final http.Response response = await _http
        .get(_uri('/v1/family/circle'), headers: await _accountHeaders())
        .timeout(const Duration(seconds: 8));
    if (response.statusCode == 404) return null;
    return FamilyCircle.fromMap(_decode(response));
  }

  Future<void> createFamilyCircle({
    required String displayName,
    required String circleName,
  }) async {
    final http.Response response = await _http
        .post(
          _uri('/v1/family/circle'),
          headers: await _accountHeaders(),
          body: jsonEncode(<String, String>{
            'display_name': displayName.trim(),
            'circle_name': circleName.trim(),
          }),
        )
        .timeout(const Duration(seconds: 8));
    _decode(response);
  }

  Future<String> createFamilyInvitation(String displayName) async {
    final http.Response response = await _http
        .post(
          _uri('/v1/family/circle/invitations'),
          headers: await _accountHeaders(),
          body: jsonEncode(<String, String>{'display_name': displayName.trim()}),
        )
        .timeout(const Duration(seconds: 8));
    return _decode(response)['invite_code']?.toString() ?? '';
  }

  Future<void> joinFamilyCircle({
    required String inviteCode,
    required String displayName,
  }) async {
    final http.Response response = await _http
        .post(
          _uri('/v1/family/join'),
          headers: await _accountHeaders(),
          body: jsonEncode(<String, String>{
            'invite_code': inviteCode.trim(),
            'display_name': displayName.trim(),
          }),
        )
        .timeout(const Duration(seconds: 8));
    _decode(response);
  }

  Future<void> shareFamilyLocation({
    required double latitude,
    required double longitude,
    required int shareMinutes,
    required bool precise,
  }) async {
    final http.Response response = await _http
        .put(
          _uri('/v1/family/location'),
          headers: await _accountHeaders(),
          body: jsonEncode(<String, dynamic>{
            'latitude': latitude,
            'longitude': longitude,
            'share_minutes': shareMinutes,
            'precision': precise ? 'precise' : 'approximate',
            'precise_location_consent': precise,
          }),
        )
        .timeout(const Duration(seconds: 8));
    _decode(response);
  }

  Future<void> stopSharingFamilyLocation() async {
    final http.Response response = await _http
        .delete(_uri('/v1/family/location'), headers: await _accountHeaders())
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 204) _decode(response);
  }

  /// «Estoy bien» o «Necesito ayuda». Con coordenadas las comparte con la
  /// familia durante [shareMinutes]; sin ellas el aviso sale igual.
  Future<void> reportFamilyStatus({
    required bool needsHelp,
    String? message,
    String? eventId,
    double? latitude,
    double? longitude,
    bool precise = false,
    int shareMinutes = 240,
  }) async {
    final String? note = _nullIfBlank(message);
    final Map<String, dynamic> body = <String, dynamic>{
      'status': needsHelp ? 'need_help' : 'safe',
      'share_minutes': shareMinutes,
      'message': ?note,
      // Un identificador que el servidor rechazaría no debe impedir el aviso.
      if (eventId != null && _eventIdPattern.hasMatch(eventId))
        'event_id': eventId,
      if (latitude != null && longitude != null)
        'location': <String, dynamic>{
          'latitude': latitude,
          'longitude': longitude,
          'precision': precise ? 'precise' : 'approximate',
          'precise_location_consent': precise,
        },
    };
    final http.Response response = await _http
        .put(
          _uri('/v1/family/status'),
          headers: await _accountHeaders(),
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 10));
    _decode(response);
  }

  Future<List<SeismicEvent>> _fetchLegacyRecentEvents() async {
    final http.Response response = await _http
        .get(_uri('/v1/events/recent'), headers: await _mobileHeaders())
        .timeout(const Duration(seconds: 8));
    return _eventsFromPayload(_decode(response));
  }

  static List<SeismicEvent> _eventsFromPayload(Map<String, dynamic> decoded) =>
      (decoded['events'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(SeismicEvent.fromMap)
          .toList(growable: false);

  /// Comprueba el estado sin decodificar en este hilo un cuerpo exitoso.
  static void _ensureSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    Object? detail;
    try {
      detail = response.body.isEmpty ? null : jsonDecode(response.body);
    } on FormatException {
      // Una página de error del proxy no es JSON: basta con el código.
      detail = null;
    }
    throw SeismikApiException(
      (detail ?? 'HTTP ${response.statusCode}').toString(),
      response.statusCode,
    );
  }

  /// Decodifica fuera del hilo de la interfaz cuando el cuerpo es grande.
  ///
  /// El historial y el catálogo de estaciones superan los 200 KB. Decodificarlos
  /// en el hilo principal detenía la animación del mapa y de la hoja durante
  /// decenas de milisegundos, y bastante más en teléfonos de gama baja.
  static Future<T> _parseInBackground<T>(
    T Function(String body) parser,
    String body,
  ) async {
    if (body.length < backgroundParseThreshold) return parser(body);
    return compute(parser, body);
  }

  Future<void> _cacheEvents(List<SeismicEvent> events) async {
    // Volver a la app suele traer los mismos sismos: si nada cambió no se
    // codifica ni se reescribe el historial guardado.
    final String signature = _eventsSignature(events);
    if (signature == _eventsCacheSignature) return;
    try {
      final String encoded = events.length < 40
          ? encodeEventsCache(events)
          : await compute(encodeEventsCache, events);
      final SharedPreferences preferences = await SharedPreferences.getInstance();
      await preferences.setString(_eventCacheKey, encoded);
      _eventsCacheSignature = signature;
    } catch (_) {
      // La caché es un respaldo: la próxima respuesta vuelve a intentarlo.
    }
  }

  /// Historial guardado en el teléfono, para mostrarlo antes que la red.
  Future<List<SeismicEvent>> readCachedEvents() async {
    try {
      final SharedPreferences preferences = await SharedPreferences.getInstance();
      final String? raw = preferences.getString(_eventCacheKey);
      if (raw == null || raw.isEmpty) return const <SeismicEvent>[];
      final List<SeismicEvent> events = await _parseInBackground(
        parseEventsBody,
        raw,
      );
      _eventsCacheSignature ??= _eventsSignature(events);
      return events;
    } catch (_) {
      return const <SeismicEvent>[];
    }
  }

  static String _eventsSignature(List<SeismicEvent> events) {
    final StringBuffer buffer = StringBuffer()..write(events.length);
    for (final SeismicEvent event in events) {
      buffer
        ..write('|')
        ..write(event.id)
        ..write('@')
        ..write(event.updatedAt?.millisecondsSinceEpoch ?? 0)
        ..write(':')
        ..write(event.magnitude);
    }
    return buffer.toString();
  }

  Uri _uri(String path) => Uri.parse('${SeismikConstants.apiBaseUrl}$path');

  Map<String, String> _jsonHeaders() => <String, String>{
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };

  Future<String?> _crowdToken() async =>
      await _secureStorage.read(key: _crowdTokenKey);

  Future<Map<String, String>> _mobileHeaders() async {
    final String? session = await _deviceSession();
    if (session == null || session.isEmpty) {
      throw const SeismikApiException('Device is not registered', null);
    }
    return <String, String>{
      ..._jsonHeaders(),
      'X-Seismik-Device-Session': session,
    };
  }

  Future<String?> _accountSession() async =>
      _accountToken ??= await _secureStorage.read(key: _accountSessionKey);

  /// Búsqueda de familiares exige cuenta. La sesión del dispositivo la
  /// acompaña cuando existe, para asociar el teléfono que recibe los avisos.
  Future<Map<String, String>> _accountHeaders({
    bool requireDevice = false,
  }) async {
    final String? account = await _accountSession();
    if (account == null || account.isEmpty) {
      throw const SeismikApiException('Account session required', 401);
    }
    final String? device = await _deviceSession();
    final bool hasDevice = device != null && device.isNotEmpty;
    if (requireDevice && !hasDevice) {
      throw const SeismikApiException('Device is not registered', null);
    }
    return <String, String>{
      ..._jsonHeaders(),
      'X-Seismik-Account-Session': account,
      if (hasDevice) 'X-Seismik-Device-Session': device,
    };
  }

  Map<String, dynamic> _decode(http.Response response) {
    final Object? decoded = response.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw SeismikApiException(decoded.toString(), response.statusCode);
    }
    if (decoded is! Map<String, dynamic>) {
      throw SeismikApiException('Unexpected API response', response.statusCode);
    }
    return decoded;
  }

  void close() => _http.close();
}

/// Catálogo de estaciones desde el cuerpo JSON de la API o de la caché.
///
/// Es una función de nivel superior para poder ejecutarse en otro isolate.
List<SeismicStation> parseStationsBody(String body) {
  final Object? decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) return const <SeismicStation>[];
  return (decoded['stations'] as List<dynamic>? ?? <dynamic>[])
      .whereType<Map<String, dynamic>>()
      .map(SeismicStation.fromMap)
      .toList(growable: false);
}

/// Sismos desde la respuesta del historial (`{"events": [...]}`) o desde la
/// caché que guardaban versiones anteriores, que era directamente la lista.
List<SeismicEvent> parseEventsBody(String body) {
  final Object? decoded = jsonDecode(body);
  final List<dynamic> items = switch (decoded) {
    final Map<String, dynamic> map =>
      map['events'] as List<dynamic>? ?? <dynamic>[],
    final List<dynamic> list => list,
    _ => <dynamic>[],
  };
  return items
      .whereType<Map<String, dynamic>>()
      .map(SeismicEvent.fromMap)
      .toList(growable: false);
}

String encodeEventsCache(List<SeismicEvent> events) =>
    jsonEncode(events.map((event) => event.toMap()).toList(growable: false));
