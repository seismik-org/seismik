import 'dart:convert';
import 'dart:io';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../core/constants.dart';
import '../core/security.dart';
import '../data/models/citizen_report.dart';
import '../data/models/pending_report.dart';
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

  @override
  String toString() => 'SeismikApiException($statusCode): $message';
}

class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  static const String _deviceIdKey = 'seismik.device_id';
  static const String _crowdTokenKey = 'seismik.crowd_token';
  static const String _deviceSessionKey = 'seismik.device_session';
  static const String _eventCacheKey = 'seismik.official_event_cache';
  static const String _alertCursorKey = 'seismik.alert_cursor';
  final http.Client _http;
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();

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
      integrityToken = await FirebaseAppCheck.instance.getToken(true);
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

  Future<List<SeismicStation>> fetchStations() async {
    final http.Response response = await _http
        .get(_uri('/v1/network/stations'), headers: await _mobileHeaders())
        .timeout(const Duration(seconds: 8));
    final Map<String, dynamic> decoded = _decode(response);
    return (decoded['stations'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(SeismicStation.fromMap)
        .toList(growable: false);
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
    try {
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
          .timeout(const Duration(seconds: 15));
      if (response.statusCode == 404) {
        return await _fetchLegacyRecentEvents();
      }
      final Map<String, dynamic> decoded = _decode(response);
      final List<SeismicEvent> events = _eventsFromPayload(decoded);
      await _cacheEvents(events);
      return events;
    } catch (_) {
      try {
        final List<SeismicEvent> events = await _fetchLegacyRecentEvents();
        await _cacheEvents(events);
        return events;
      } catch (_) {
        final List<SeismicEvent> cached = await _readCachedEvents();
        if (cached.isNotEmpty) return cached;
        rethrow;
      }
    }
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

  Future<void> _cacheEvents(List<SeismicEvent> events) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(
      _eventCacheKey,
      jsonEncode(events.map((event) => event.toMap()).toList(growable: false)),
    );
  }

  Future<List<SeismicEvent>> _readCachedEvents() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? raw = preferences.getString(_eventCacheKey);
    if (raw == null) return <SeismicEvent>[];
    final Object? decoded = jsonDecode(raw);
    if (decoded is! List<dynamic>) return <SeismicEvent>[];
    return decoded
        .whereType<Map<String, dynamic>>()
        .map(SeismicEvent.fromMap)
        .toList(growable: false);
  }

  Uri _uri(String path) => Uri.parse('${SeismikConstants.apiBaseUrl}$path');

  Map<String, String> _jsonHeaders() => <String, String>{
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };

  Future<String?> _crowdToken() async =>
      await _secureStorage.read(key: _crowdTokenKey);

  Future<Map<String, String>> _mobileHeaders() async {
    final String? session = await _secureStorage.read(key: _deviceSessionKey);
    if (session == null || session.isEmpty) {
      throw const SeismikApiException('Device is not registered', null);
    }
    return <String, String>{
      ..._jsonHeaders(),
      'X-Seismik-Device-Session': session,
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
