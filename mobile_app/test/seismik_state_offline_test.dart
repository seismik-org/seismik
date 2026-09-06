import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/citizen_report.dart';
import 'package:seismik/data/models/pending_report.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/offline_queue.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Cliente controlado: decide si "hay red" y registra lo que se envió.
class _FakeApiClient extends ApiClient {
  _FakeApiClient({this.online = true, this.permanentFailure = false});

  bool online;
  bool permanentFailure;
  List<SeismicEvent> missedAlerts = <SeismicEvent>[];
  final List<String> sent = <String>[];

  @override
  Future<ReportResult> sendReport(
    String path,
    Map<String, dynamic> payload,
  ) async {
    if (permanentFailure) {
      throw const SeismikApiException('cuerpo inválido', 422);
    }
    if (!online) {
      throw const SeismikApiException('sin conexión', null);
    }
    sent.add('$path:${payload['report_id']}');
    return ReportResult(
      accepted: true,
      duplicate: false,
      reportId: (payload['report_id'] ?? '').toString(),
      locationPrecision: 'approximate',
      emergencyActionRecommended: false,
      agencyRoutes: const <AgencyRoute>[],
      notice: '',
    );
  }

  @override
  Future<List<SeismicEvent>> fetchMissedAlerts() async {
    if (!online) throw const SeismikApiException('sin conexión', null);
    return missedAlerts;
  }
}

Map<String, dynamic> feltPayload(String reportId) => <String, dynamic>{
  'report_id': reportId,
  'type': 'seismik_felt_report',
  'felt': true,
};

SeismicEvent alert(String id) => SeismicEvent.fromMap(<String, dynamic>{
  'event_id': id,
  'type': 'earthquake_candidate',
  'detected_at': '2026-08-30T12:00:00Z',
  'latitude': 4.65,
  'longitude': -74.05,
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MobileSettings settings;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    settings = MobileSettings();
    await settings.load();
  });

  test('sin conexión el reporte se guarda y se informa a la persona', () async {
    final _FakeApiClient api = _FakeApiClient(online: false);
    final SeismikState state = SeismikState(settings: settings, apiClient: api);

    final ReportResult result = await state.submitReport(
      kind: PendingReportKind.felt,
      payload: feltPayload('report-1'),
      preciseLocation: false,
    );

    expect(result.queuedOffline, isTrue);
    expect(result.reportId, 'report-1');
    expect(result.notice, contains('Sin conexión'));
    expect(state.pendingReportCount, 1);
    expect(api.sent, isEmpty);
  });

  test('al volver la red la cola se vacía con el mismo report_id', () async {
    final _FakeApiClient api = _FakeApiClient(online: false);
    final SeismikState state = SeismikState(settings: settings, apiClient: api);
    await state.submitReport(
      kind: PendingReportKind.felt,
      payload: feltPayload('report-1'),
      preciseLocation: false,
    );

    api.online = true;
    await state.flushPendingReports();

    expect(api.sent, <String>['/v1/reports/felt:report-1']);
    expect(state.pendingReportCount, 0);
    expect(state.syncMessage, contains('1 reporte'));
  });

  test('con red el reporte se envía de inmediato', () async {
    final _FakeApiClient api = _FakeApiClient();
    final SeismikState state = SeismikState(settings: settings, apiClient: api);

    final ReportResult result = await state.submitReport(
      kind: PendingReportKind.damage,
      payload: feltPayload('report-2'),
      preciseLocation: true,
    );

    expect(result.queuedOffline, isFalse);
    expect(result.accepted, isTrue);
    expect(api.sent, <String>['/v1/reports/damage:report-2']);
    expect(state.pendingReportCount, 0);
  });

  test('un rechazo definitivo se propaga y no llena la cola', () async {
    final _FakeApiClient api = _FakeApiClient(permanentFailure: true);
    final SeismikState state = SeismikState(settings: settings, apiClient: api);

    await expectLater(
      state.submitReport(
        kind: PendingReportKind.felt,
        payload: feltPayload('report-3'),
        preciseLocation: false,
      ),
      throwsA(isA<SeismikApiException>()),
    );
    expect(state.pendingReportCount, 0);
  });

  test('un reporte encolado que el servidor rechaza sale de la cola', () async {
    final _FakeApiClient api = _FakeApiClient(online: false);
    final SeismikState state = SeismikState(settings: settings, apiClient: api);
    await state.submitReport(
      kind: PendingReportKind.felt,
      payload: feltPayload('report-4'),
      preciseLocation: false,
    );

    api.online = true;
    api.permanentFailure = true;
    await state.flushPendingReports();

    expect(state.pendingReportCount, 0);
    expect(await const OfflineReportQueue().pendingCount(), 0);
  });

  test('las alertas perdidas se incorporan al historial sin duplicar', () async {
    final _FakeApiClient api = _FakeApiClient()
      ..missedAlerts = <SeismicEvent>[alert('drill-1'), alert('drill-2')];
    final SeismikState state = SeismikState(settings: settings, apiClient: api);

    await state.syncMissedAlerts();
    expect(state.recentEvents.map((event) => event.id), <String>[
      'drill-2',
      'drill-1',
    ]);
    expect(state.syncMessage, contains('2 alertas'));

    await state.syncMissedAlerts();
    expect(state.recentEvents, hasLength(2));
  });

  test('sin red la sincronización de alertas no rompe el monitor', () async {
    final _FakeApiClient api = _FakeApiClient(online: false);
    final SeismikState state = SeismikState(settings: settings, apiClient: api);

    await state.syncMissedAlerts();

    expect(state.recentEvents, isEmpty);
  });

  test('seleccionar un evento lo expone para el mapa y la hoja', () async {
    final SeismikState state = SeismikState(
      settings: settings,
      apiClient: _FakeApiClient(),
    );

    state.selectEvent(alert('drill-9'));
    expect(state.selectedEvent?.id, 'drill-9');
    state.selectEvent(null);
    expect(state.selectedEvent, isNull);
  });
}
