import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/data/models/station.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Cuenta las descargas y permite retener una en curso.
class _CountingApiClient extends ApiClient {
  int historyRequests = 0;
  final List<int> requestedDays = <int>[];
  Completer<void>? gate;
  List<SeismicEvent> history = <SeismicEvent>[];
  List<SeismicEvent> missedAlerts = <SeismicEvent>[];

  @override
  Future<List<SeismicEvent>> fetchRecentEvents({
    Set<String> sourceIds = const <String>{'sgc_colombia', 'usgs_global'},
    int days = 7,
    double minimumMagnitude = 2.5,
  }) async {
    historyRequests++;
    requestedDays.add(days);
    await gate?.future;
    return history;
  }

  @override
  Future<List<SeismicStation>> fetchStations({bool forceRefresh = false}) async =>
      const <SeismicStation>[];

  @override
  Future<List<SeismicEvent>> fetchMissedAlerts() async => missedAlerts;
}

SeismicEvent event(String id, {String type = 'official_report_update'}) =>
    SeismicEvent.fromMap(<String, dynamic>{
      'event_id': id,
      'type': type,
      'origin_time': '2026-09-12T12:00:00Z',
      'latitude': 4.65,
      'longitude': -74.05,
    });

Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 80));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MobileSettings settings;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    settings = MobileSettings();
    await settings.load();
  });

  SeismikState stateWith(_CountingApiClient api) => SeismikState(
    settings: settings,
    apiClient: api,
    settingsDebounce: const Duration(milliseconds: 20),
  );

  test('refrescos simultáneos comparten una sola descarga', () async {
    final _CountingApiClient api = _CountingApiClient()
      ..gate = Completer<void>()
      ..history = <SeismicEvent>[event('a')];
    final SeismikState state = stateWith(api);

    final Future<void> pullToRefresh = state.refreshNetworkData();
    final Future<void> resumed = state.refreshNetworkData();
    api.gate!.complete();
    await Future.wait(<Future<void>>[pullToRefresh, resumed]);

    expect(api.historyRequests, 1);
    expect(state.recentEvents.single.id, 'a');
    expect(state.networkOnline, isTrue);
  });

  test('cambiar el tema o el color no descarga nada', () async {
    final _CountingApiClient api = _CountingApiClient();
    stateWith(api);

    await settings.setThemeMode(ThemeMode.dark);
    await settings.setUseDynamicColor(false);
    await settle();

    expect(api.historyRequests, 0);
  });

  test('una ráfaga de cambios de filtro produce una sola descarga', () async {
    final _CountingApiClient api = _CountingApiClient();
    stateWith(api);

    await settings.setHistoryDays(3);
    await settings.setHistoryDays(14);
    await settings.setMinimumHistoryMagnitude(3.5);
    await settle();

    expect(api.historyRequests, 1);
    expect(api.requestedDays.single, 14);
  });

  test('un filtro cambiado durante una descarga se aplica al terminar', () async {
    final _CountingApiClient api = _CountingApiClient()..gate = Completer<void>();
    final SeismikState state = stateWith(api);

    final Future<void> running = state.refreshNetworkData();
    await settings.setHistoryDays(30);
    await settle();
    expect(api.historyRequests, 1, reason: 'no se lanza otra en paralelo');

    api.gate!.complete();
    await running;
    expect(api.requestedDays, <int>[7, 30]);
  });

  test('las alertas recuperadas no desaparecen al refrescar el historial', () async {
    final _CountingApiClient api = _CountingApiClient()
      ..missedAlerts = <SeismicEvent>[
        event('drill-1', type: 'earthquake_candidate'),
      ]
      ..history = <SeismicEvent>[event('oficial-1')];
    final SeismikState state = stateWith(api);

    await state.syncMissedAlerts();
    api.missedAlerts = <SeismicEvent>[];
    await state.refreshNetworkData();

    expect(state.recentEvents.map((item) => item.id), <String>[
      'drill-1',
      'oficial-1',
    ]);
  });

  test('tocar el mapa sin nada seleccionado no reconstruye la pantalla', () {
    final SeismikState state = stateWith(_CountingApiClient());
    int notifications = 0;
    state.addListener(() => notifications++);

    state.selectEvent(null);
    state.selectEvent(null);

    expect(notifications, 0);
  });
}
