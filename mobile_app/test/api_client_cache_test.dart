import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/data/models/station.dart';
import 'package:seismik/services/api_client.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String stationsPath = '/v1/network/stations';

/// Cuerpos grandes a propósito: superan el umbral y se decodifican en otro
/// isolate, igual que el catálogo real (~240 KB) y el historial (~250 KB).
String stationsBody(int count) => jsonEncode(<String, dynamic>{
  'stations': <Map<String, dynamic>>[
    for (int index = 0; index < count; index++)
      <String, dynamic>{
        'station_id': 'S$index',
        'network': 'CM',
        'latitude': 4.0 + index / 1000,
        'longitude': -74.0,
        'country_code': 'CO',
      },
  ],
});

String historyBody(int count) => jsonEncode(<String, dynamic>{
  'events': <Map<String, dynamic>>[
    for (int index = 0; index < count; index++)
      <String, dynamic>{
        'event_id': 'evt-$index',
        'type': 'official_report_update',
        'origin_time': '2026-09-12T12:00:00Z',
        'latitude': 4.6,
        'longitude': -74.1,
        'magnitude': 3.1,
        'place': 'Lugar de prueba numero $index, Colombia',
        'stations': <dynamic>[],
      },
  ],
});

MockClient serving(
  List<String> paths, {
  int stationsStatus = 200,
  int historyStatus = 200,
}) => MockClient((http.Request request) async {
  paths.add(request.url.path);
  return switch (request.url.path) {
    stationsPath => http.Response(
      stationsStatus == 200 ? stationsBody(900) : '{"detail":"caido"}',
      stationsStatus,
    ),
    '/v1/events/history' => http.Response(
      historyStatus == 200 ? historyBody(200) : '{"detail":"caido"}',
      historyStatus,
    ),
    '/v1/events/recent' => http.Response(historyBody(3), 200),
    _ => http.Response('{}', 404),
  };
});

int stationDownloads(List<String> paths) =>
    paths.where((path) => path == stationsPath).length;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'seismik.device_session': 'session-1',
    });
  });

  test('las estaciones se descargan una vez y luego salen de la memoria', () async {
    final List<String> paths = <String>[];
    final ApiClient api = ApiClient(httpClient: serving(paths));

    final List<SeismicStation> first = await api.fetchStations();
    final List<SeismicStation> second = await api.fetchStations();

    expect(first, hasLength(900));
    expect(
      identical(first, second),
      isTrue,
      reason: 'la misma lista evita reconstruir los marcadores del mapa',
    );
    expect(stationDownloads(paths), 1);
  });

  test('al abrir la app con caché vigente no se descarga el catálogo', () async {
    final List<String> paths = <String>[];
    await ApiClient(httpClient: serving(paths)).fetchStations();

    final ApiClient reopened = ApiClient(httpClient: serving(paths));
    expect(await reopened.readCachedStations(), hasLength(900));
    expect(await reopened.fetchStations(), hasLength(900));
    expect(stationDownloads(paths), 1);
  });

  test('con la caché vencida intenta renovarla y, sin red, usa la guardada', () async {
    final List<String> paths = <String>[];
    await ApiClient(httpClient: serving(paths)).fetchStations();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setInt(
      'seismik.stations_cached_at',
      DateTime.now().subtract(const Duration(days: 2)).millisecondsSinceEpoch,
    );

    final ApiClient offline = ApiClient(
      httpClient: serving(paths, stationsStatus: 503),
    );

    expect(await offline.fetchStations(), hasLength(900));
    expect(stationDownloads(paths), 2);
  });

  test('sin caché ni red el error llega a quien llama', () async {
    final ApiClient api = ApiClient(
      httpClient: serving(<String>[], stationsStatus: 503),
    );

    await expectLater(api.fetchStations(), throwsA(isA<SeismikApiException>()));
  });

  test('el historial grande se decodifica y queda guardado para la próxima apertura', () async {
    final ApiClient api = ApiClient(httpClient: serving(<String>[]));

    final List<SeismicEvent> events = await api.fetchRecentEvents();
    expect(events, hasLength(200));
    expect(events.first.place, 'Lugar de prueba numero 0, Colombia');

    // La caché se escribe sin bloquear la respuesta: se espera a que termine.
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    for (int attempt = 0; attempt < 100; attempt++) {
      if (preferences.getString('seismik.official_event_cache') != null) break;
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    final ApiClient reopened = ApiClient(httpClient: serving(<String>[]));
    expect(await reopened.readCachedEvents(), hasLength(200));
  });

  test('un fallo del historial no espera además a la ruta antigua', () async {
    final List<String> paths = <String>[];
    final ApiClient api = ApiClient(
      httpClient: serving(paths, historyStatus: 502),
    );

    await expectLater(
      api.fetchRecentEvents(),
      throwsA(isA<SeismikApiException>()),
    );
    expect(paths, isNot(contains('/v1/events/recent')));
  });

  test('sólo un servidor antiguo (404) usa la ruta anterior', () async {
    final List<String> paths = <String>[];
    final ApiClient api = ApiClient(
      httpClient: serving(paths, historyStatus: 404),
    );

    expect(await api.fetchRecentEvents(), hasLength(3));
    expect(paths, contains('/v1/events/recent'));
  });

  test('la caché de versiones anteriores, que era una lista, se sigue leyendo', () {
    final List<SeismicEvent> events = parseEventsBody(
      jsonEncode(<Map<String, dynamic>>[
        <String, dynamic>{
          'event_id': 'viejo',
          'type': 'official_report_update',
          'origin_time': '2026-09-01T00:00:00Z',
        },
      ]),
    );

    expect(events.single.id, 'viejo');
  });
}
