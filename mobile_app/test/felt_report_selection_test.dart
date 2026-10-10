import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seismik/data/models/citizen_report.dart';
import 'package:seismik/data/models/pending_report.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/presentation/screens/felt_report_screen.dart';
import 'package:seismik/presentation/widgets/adaptive.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';

class _Api extends ApiClient {
  final quake = SeismicEvent(
    id: 'real-quake',
    type: 'official_report_update',
    detectedAt: DateTime.now().subtract(const Duration(hours: 1)),
    latitude: 4.6,
    longitude: -74,
    place: 'Bogotá',
    officialEventId: 'sgc-1',
    countryCode: 'CO',
  );
  @override
  Future<List<SeismicEvent>> fetchRecentEvents({
    Set<String> sourceIds = const <String>{},
    int days = 7,
    double minimumMagnitude = 2.5,
  }) async => <SeismicEvent>[quake];
  @override
  Future<List<AgencyRoute>> fetchReportingAgencies({
    required String countryCode,
    String? officialEventId,
  }) async => OfficialAgencyCatalog.fallbackFor(
    countryCode: countryCode,
    officialEventId: officialEventId,
  );
}

class _State extends SeismikState {
  _State(MobileSettings settings, _Api api)
    : super(settings: settings, apiClient: api);
  Map<String, dynamic>? submitted;
  @override
  Future<({double latitude, double longitude})?> currentCoordinates() async =>
      (latitude: 4.6, longitude: -74.0);
  @override
  Future<ReportResult> submitReport({
    required PendingReportKind kind,
    required Map<String, dynamic> payload,
    required bool preciseLocation,
    bool emergencyActionRecommended = false,
  }) async {
    submitted = payload;
    return const ReportResult(
      accepted: true,
      duplicate: false,
      reportId: 'r',
      locationPrecision: 'approximate',
      emergencyActionRecommended: false,
      agencyRoutes: <AgencyRoute>[],
      notice: 'OK',
    );
  }
}

void main() {
  for (final platform in <TargetPlatform>[
    TargetPlatform.android,
    TargetPlatform.iOS,
  ]) {
    testWidgets(
      '$platform requires explicit quake and felt choice, submits selected IDs',
      (tester) async {
        debugDefaultTargetPlatformOverride = platform;
        addTearDown(() => debugDefaultTargetPlatformOverride = null);
        tester.view.physicalSize = const Size(800, 3000);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        SharedPreferences.setMockInitialValues(<String, Object>{});
        final settings = MobileSettings();
        final api = _Api();
        final state = _State(settings, api);
        addTearDown(state.dispose);
        await tester.pumpWidget(
          MultiProvider(
            providers: [
              ChangeNotifierProvider<MobileSettings>.value(value: settings),
              ChangeNotifierProvider<SeismikState>.value(value: state),
            ],
            child: MaterialApp(home: FeltReportScreen(event: api.quake)),
          ),
        );
        await tester.pumpAndSettle();
        AdaptiveButton send() => tester.widget<AdaptiveButton>(
          find.widgetWithText(AdaptiveButton, 'Enviar a Seismik'),
        );
        expect(
          send().onPressed,
          isNull,
          reason: 'Opening from a quake does not select it or answer yes',
        );
        await tester.tap(find.text('Elegir sismo'));
        await tester.pumpAndSettle();
        await tester.tap(find.textContaining('Bogotá').first);
        await tester.pumpAndSettle();
        expect(send().onPressed, isNull);
        await tester.ensureVisible(find.text('No lo sentí'));
        await tester.tap(find.text('No lo sentí'));
        await tester.pumpAndSettle();
        expect(send().onPressed, isNotNull);
        await tester.ensureVisible(find.text('Enviar a Seismik'));
        await tester.tap(find.text('Enviar a Seismik'));
        await tester.pumpAndSettle();
        expect(state.submitted?['earthquake_event_id'], 'real-quake');
        expect(state.submitted?['official_event_id'], 'sgc-1');
        expect(state.submitted?['felt'], false);
        expect(state.submitted?['intensity_mmi'], isNull);
        tester.state<NavigatorState>(find.byType(Navigator).first).pop();
        await tester.pumpAndSettle();
        expect(send().onPressed, isNull, reason: 'The next report needs a new selection and answer');
        debugDefaultTargetPlatformOverride = null;
      },
    );
  }
}
