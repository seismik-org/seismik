import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik/services/adaptive_transfer.dart';
import 'package:seismik/services/api_client.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'seismik.device_session': 'session-1',
    });
  });

  test('starts light, upgrades, degrades and recovers with hysteresis', () {
    final AdaptiveTransfer profile = AdaptiveTransfer();
    expect(profile.eventLimit, 50);
    profile.succeeded(const Duration(milliseconds: 500), 20000);
    profile.succeeded(const Duration(milliseconds: 500), 20000);
    expect(profile.eventLimit, 200);
    profile.succeeded(const Duration(seconds: 6), 20000);
    expect(profile.eventLimit, 30);
    expect(profile.timeout.inSeconds, 40);
    profile.succeeded(const Duration(seconds: 1), 20000);
    profile.succeeded(const Duration(seconds: 1), 20000);
    expect(profile.constrained, isTrue);
    profile.succeeded(const Duration(seconds: 1), 20000);
    expect(profile.constrained, isFalse);
    profile.failed();
    expect(profile.eventLimit, 30);
  });

  test(
    'weak network requests small history and defers heavy stations',
    () async {
      final List<http.Request> requests = <http.Request>[];
      final ApiClient api = ApiClient(
        httpClient: MockClient((request) async {
          requests.add(request);
          return http.Response(
            jsonEncode(<String, dynamic>{'events': <dynamic>[]}),
            200,
          );
        }),
      );
      api.transfer.failed();
      await api.fetchRecentEvents();
      expect(requests.single.url.queryParameters['limit'], '30');
      expect(requests.single.headers['Accept-Encoding'], 'gzip');
      expect(requests.single.headers['X-Seismik-Device-Session'], 'session-1');
      expect(await api.fetchStations(), isEmpty);
      expect(requests, hasLength(1));
      api.close();
    },
  );
}
