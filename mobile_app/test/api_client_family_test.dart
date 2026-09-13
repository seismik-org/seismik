import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik/data/models/family_circle.dart';
import 'package:seismik/data/models/seismik_account.dart';
import 'package:seismik/services/api_client.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'seismik.device_session': 'device-1',
    });
  });

  test('sin cuenta la familia pide iniciar sesión sin llamar al servidor', () async {
    final List<http.Request> requests = <http.Request>[];
    final ApiClient api = ApiClient(
      httpClient: MockClient((http.Request request) async {
        requests.add(request);
        return http.Response('{}', 200);
      }),
    );

    await expectLater(
      api.fetchFamilyCircle(),
      throwsA(
        isA<SeismikApiException>().having(
          (error) => error.isUnauthorized,
          'isUnauthorized',
          isTrue,
        ),
      ),
    );
    expect(requests, isEmpty);
  });

  test('el código se canjea con el verificador y la sesión viaja en cada petición', () async {
    final List<http.Request> requests = <http.Request>[];
    final ApiClient api = ApiClient(
      httpClient: MockClient((http.Request request) async {
        requests.add(request);
        if (request.url.path == '/v1/oauth/mobile/exchange') {
          return http.Response(
            jsonEncode(<String, String>{
              'mobile_session_token': 'account-token',
              'uid': 'google-1',
              'email': 'ana@example.test',
              'name': 'Ana Maria',
            }),
            200,
          );
        }
        return http.Response('{"detail":"No family circle found"}', 404);
      }),
    );

    final SeismikAccount account = await api.exchangeOAuthCode(
      code: 'codigo',
      verifier: 'v' * 43,
    );
    expect(account.firstName, 'Ana');
    final http.Request exchange = requests.single;
    expect(exchange.url.host, 'auth.seismik.org');
    expect(jsonDecode(exchange.body), <String, String>{
      'code': 'codigo',
      'code_verifier': 'v' * 43,
    });

    expect(await api.fetchFamilyCircle(), isNull);
    expect(requests.last.headers['X-Seismik-Account-Session'], 'account-token');
    expect(requests.last.headers['X-Seismik-Device-Session'], 'device-1');

    final ApiClient reopened = ApiClient(
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );
    expect((await reopened.currentAccount())?.email, 'ana@example.test');

    await reopened.clearAccount();
    expect(await reopened.currentAccount(), isNull);
  });

  test('el aviso de estado envía la ubicación sólo si la hay', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'seismik.device_session': 'device-1',
      'seismik.account_session': 'account-token',
    });
    final List<Map<String, dynamic>> bodies = <Map<String, dynamic>>[];
    final ApiClient api = ApiClient(
      httpClient: MockClient((http.Request request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/v1/family/status');
        bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response('{"status":"safe"}', 200);
      }),
    );

    await api.reportFamilyStatus(
      needsHelp: true,
      eventId: 'official-sgc-1',
      latitude: 4.65,
      longitude: -74.1,
    );
    await api.reportFamilyStatus(needsHelp: false, eventId: 'evento con espacios');

    expect(bodies.first['status'], 'need_help');
    expect(bodies.first['event_id'], 'official-sgc-1');
    expect(bodies.first['location'], <String, dynamic>{
      'latitude': 4.65,
      'longitude': -74.1,
      'precision': 'approximate',
      'precise_location_consent': false,
    });
    expect(bodies.last['status'], 'safe');
    expect(bodies.last.containsKey('location'), isFalse);
    expect(
      bodies.last.containsKey('event_id'),
      isFalse,
      reason: 'un identificador que el servidor rechazaría no debe impedir el aviso',
    );
  });

  test('el círculo trae estado, ubicación y propiedad de cada integrante', () {
    final FamilyCircle circle = FamilyCircle.fromMap(<String, dynamic>{
      'circle_id': 'casa',
      'circle_name': 'Casa',
      'is_owner': true,
      'members': <Map<String, dynamic>>[
        <String, dynamic>{
          'member_id': 'a1',
          'display_name': 'Óscar',
          'is_you': true,
          'is_owner': true,
          'location': null,
          'status': null,
        },
        <String, dynamic>{
          'member_id': 'b2',
          'display_name': 'Ana',
          'is_you': false,
          'is_owner': false,
          'location': <String, dynamic>{
            'latitude': 4.65,
            'longitude': -74.08,
            'precision': 'approximate',
            'shared_at': '2026-09-12T20:00:00+00:00',
            'expires_at': '2026-09-13T00:00:00+00:00',
          },
          'status': <String, dynamic>{
            'status': 'need_help',
            'message': 'Estoy en el parque',
            'event_id': 'official-1',
            'reported_at': '2026-09-12T20:00:00+00:00',
          },
        },
      ],
    });

    expect(circle.isOwner, isTrue);
    expect(circle.you?.displayName, 'Óscar');
    final FamilyMember ana = circle.members.last;
    expect(ana.initial, 'A');
    expect(ana.status?.needsHelp, isTrue);
    expect(ana.status?.message, 'Estoy en el parque');
    expect(ana.location?.latitude, 4.65);
  });
}
