import 'dart:convert';
import 'dart:io';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../core/constants.dart';
import '../core/security.dart';
import '../data/models/citizen_report.dart';
import '../data/models/seismic_event.dart';
import '../data/models/station.dart';

class SeismikApiException implements Exception {
  const SeismikApiException(this.message, this.statusCode);
  final String message;
  final int? statusCode;

  @override
  String toString() => 'SeismikApiException($statusCode): $message';
}

class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  static const String _deviceIdKey = 'seismik.device_id';
  static const String _crowdTokenKey = 'seismik.crowd_token';
  final http.Client _http;

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
  }) async {
    final String deviceId = await ensureDeviceId();
    final String? integrityToken = await FirebaseAppCheck.instance.getToken(
      true,
    );
    if (integrityToken == null) {
      throw const SeismikApiException('App Check did not return a token', null);
    }
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
      'locale': Platform.localeName,
      'country_code': _localeCountryCode(),
      'app_attest_token': Platform.isIOS ? integrityToken : null,
      'play_integrity_token': Platform.isAndroid ? integrityToken : null,
    };
    final http.Response response = await _http
        .post(
          _uri('/v1/devices/register'),
          headers: _jsonHeaders(deviceKey: true),
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 8));
    final Map<String, dynamic> decoded = _decode(response);
    final String? crowdToken = decoded['crowd_token']?.toString();
    if (crowdToken == null || crowdToken.isEmpty) {
      throw SeismikApiException(
        'Registration omitted crowd token',
        response.statusCode,
      );
    }
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_crowdTokenKey, crowdToken);
  }

  Future<void> sendShake({
    required double latitude,
    required double longitude,
    required double pgaG,
    required int timestampMilliseconds,
  }) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? token = preferences.getString(_crowdTokenKey);
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

  Future<ReportResult> submitFeltReport({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
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
    final Map<String, dynamic> payload =
        await _reportBase(
            latitude: latitude,
            longitude: longitude,
            countryCode: countryCode,
            preciseLocation: preciseLocation,
            shareWithOfficialAgencies: shareWithOfficialAgencies,
            earthquakeEventId: earthquakeEventId,
            officialEventId: officialEventId,
            comment: comment,
          )
          ..addAll(<String, dynamic>{
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
    return ReportResult.fromMap(await _postSigned('/v1/reports/felt', payload));
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
    final Map<String, dynamic> payload =
        await _reportBase(
            latitude: latitude,
            longitude: longitude,
            countryCode: countryCode,
            preciseLocation: preciseLocation,
            shareWithOfficialAgencies: shareWithOfficialAgencies,
            earthquakeEventId: earthquakeEventId,
            officialEventId: officialEventId,
            comment: comment,
          )
          ..addAll(<String, dynamic>{
            'type': 'seismik_damage_report',
            'severity': severity,
            'hazards': hazards,
            'building_type': _nullIfBlank(buildingType),
            'people_trapped': peopleTrapped,
            'injuries_observed': injuriesObserved,
            'emergency_services_contacted': emergencyServicesContacted,
            'safe_to_remain': safeToRemain,
          });
    return ReportResult.fromMap(
      await _postSigned('/v1/reports/damage', payload),
    );
  }

  Future<Map<String, dynamic>> _reportBase({
    required double latitude,
    required double longitude,
    required String countryCode,
    required bool preciseLocation,
    required bool shareWithOfficialAgencies,
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
    'consent_version': '2026-08',
    'comment': _nullIfBlank(comment),
  };

  Future<Map<String, dynamic>> _postSigned(
    String path,
    Map<String, dynamic> payload,
  ) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final String? token = preferences.getString(_crowdTokenKey);
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
        .get(_uri('/v1/network/stations'), headers: _jsonHeaders())
        .timeout(const Duration(seconds: 8));
    final Map<String, dynamic> decoded = _decode(response);
    return (decoded['stations'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(SeismicStation.fromMap)
        .toList(growable: false);
  }

  Future<List<SeismicEvent>> fetchRecentEvents() async {
    final http.Response response = await _http
        .get(_uri('/v1/events/recent'), headers: _jsonHeaders())
        .timeout(const Duration(seconds: 8));
    final Map<String, dynamic> decoded = _decode(response);
    return (decoded['events'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(SeismicEvent.fromMap)
        .toList(growable: false);
  }

  Uri _uri(String path) => Uri.parse('${SeismikConstants.apiBaseUrl}$path');

  Map<String, String> _jsonHeaders({bool deviceKey = false}) =>
      <String, String>{
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (deviceKey) 'X-Seismik-Device-Key': SeismikConstants.deviceApiKey,
      };

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
