import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:seismik/data/models/pending_report.dart';
import 'package:seismik/presentation/screens/offline_emergency_screen.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/emergency_store.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });
  test(
    'mode and local notes survive reopening without authentication',
    () async {
      expect(await EmergencyStore.enabled(), isFalse);
      await EmergencyStore.setEnabled(true);
      await EmergencyStore.saveNotes('Nos encontramos en el parque');
      expect(await EmergencyStore.enabled(), isTrue);
      expect(await EmergencyStore.notes(), 'Nos encontramos en el parque');
      expect(await EmergencyStore.cachedAt(), isNull);
    },
  );
  test('offline mode enqueues the exact report without calling HTTP', () async {
    int requests = 0;
    final ApiClient api = ApiClient(
      httpClient: MockClient((_) async {
        requests++;
        return http.Response('{}', 503);
      }),
    );
    final SeismikState state = SeismikState(
      apiClient: api,
      settings: MobileSettings(),
    );
    await state.setOfflineEmergencyMode(true);
    await state.submitReport(
      kind: PendingReportKind.felt,
      payload: <String, dynamic>{
        'report_id': 'offline-1',
        'observed_at': '2026-10-11T12:00:00Z',
      },
      preciseLocation: false,
    );
    await state.flushPendingReports();
    expect(requests, 0);
    expect(state.pendingReportCount, 1);
    expect((await state.reportQueue.load()).single.reportId, 'offline-1');
    state.dispose();
  });
  testWidgets(
    'emergency guide opens with empty cache, no session and no HTTP',
    (tester) async {
      int requests = 0;
      final ApiClient api = ApiClient(
        httpClient: MockClient((_) async {
          requests++;
          return http.Response('{}', 503);
        }),
      );
      final SeismikState state = SeismikState(
        apiClient: api,
        settings: MobileSettings(),
      );
      await tester.pumpWidget(
        ChangeNotifierProvider<SeismikState>.value(
          value: state,
          child: const MaterialApp(home: OfflineEmergencyScreen()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Si está temblando'), findsOneWidget);
      expect(find.text('Agáchate'), findsOneWidget);
      expect(
        find.textContaining('no confirma que alguien esté a salvo'),
        findsOneWidget,
      );
      expect(requests, 0);
      await tester.pumpWidget(const SizedBox.shrink());
      state.dispose();
    },
  );
}
