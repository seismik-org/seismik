import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/connectivity_watcher.dart';
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

  test('the mode follows the signal and only stays on when pinned', () {
    expect(emergencyModeWanted(hasSignal: false, pinned: false), isTrue);
    expect(emergencyModeWanted(hasSignal: true, pinned: false), isFalse);
    expect(emergencyModeWanted(hasSignal: true, pinned: true), isTrue);
    expect(emergencyModeWanted(hasSignal: false, pinned: true), isTrue);
  });

  test('a network counts as signal when any interface is not "none"', () {
    expect(hasSignalIn(<ConnectivityResult>[ConnectivityResult.none]), isFalse);
    expect(hasSignalIn(<ConnectivityResult>[]), isFalse);
    expect(
      hasSignalIn(<ConnectivityResult>[ConnectivityResult.mobile]),
      isTrue,
    );
    expect(
      hasSignalIn(<ConnectivityResult>[
        ConnectivityResult.none,
        ConnectivityResult.wifi,
      ]),
      isTrue,
    );
  });

  test(
    'a short cut does not trigger the mode but a lasting one does',
    () async {
      final StreamController<List<ConnectivityResult>> changes =
          StreamController<List<ConnectivityResult>>();
      final List<bool> seen = <bool>[];
      final ConnectivityWatcher watcher = ConnectivityWatcher(
        changes: changes.stream,
        current: () async => <ConnectivityResult>[ConnectivityResult.wifi],
        lostAfter: const Duration(milliseconds: 80),
        backAfter: const Duration(milliseconds: 20),
      );
      await watcher.start(seen.add);
      await Future<void>.delayed(const Duration(milliseconds: 60));
      expect(seen, <bool>[true]);

      changes.add(<ConnectivityResult>[ConnectivityResult.none]);
      await Future<void>.delayed(const Duration(milliseconds: 30));
      changes.add(<ConnectivityResult>[ConnectivityResult.mobile]); // un túnel
      await Future<void>.delayed(const Duration(milliseconds: 120));
      expect(seen, <bool>[true], reason: 'el corte breve no cambió nada');

      changes.add(<ConnectivityResult>[ConnectivityResult.none]);
      await Future<void>.delayed(const Duration(milliseconds: 140));
      expect(seen, <bool>[true, false]);

      changes.add(<ConnectivityResult>[ConnectivityResult.wifi]);
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect(seen, <bool>[true, false, true]);

      await watcher.dispose();
      await changes.close();
    },
  );

  SeismikState build(int Function() onRequest) => SeismikState(
    apiClient: ApiClient(
      httpClient: MockClient((_) async {
        onRequest();
        return http.Response('{}', 503);
      }),
    ),
    settings: MobileSettings(),
  );

  test(
    'losing the signal turns the mode on and it never touches the network',
    () async {
      int requests = 0;
      final SeismikState state = build(() => ++requests);

      await state.onSignalChangedForTesting(false);

      expect(state.hasSignal, isFalse);
      expect(state.offlineEmergencyMode, isTrue);
      expect(await EmergencyStore.enabled(), isTrue);
      expect(requests, 0);
      state.dispose();
    },
  );

  test('getting the signal back turns it off by itself', () async {
    final SeismikState state = build(() => 0);
    await state.onSignalChangedForTesting(false);

    await state.onSignalChangedForTesting(true);

    expect(state.offlineEmergencyMode, isFalse);
    expect(await EmergencyStore.enabled(), isFalse);
    state.dispose();
  });

  test(
    'pinned mode survives the signal and only the person turns it off',
    () async {
      final SeismikState state = build(() => 0);
      await state.setEmergencyPinned(true);
      expect(state.offlineEmergencyMode, isTrue);

      await state.onSignalChangedForTesting(true);
      expect(state.offlineEmergencyMode, isTrue, reason: 'lo fijó la persona');

      await state.setEmergencyPinned(false);
      expect(state.offlineEmergencyMode, isFalse);
      expect(await EmergencyStore.pinned(), isFalse);
      state.dispose();
    },
  );

  test('"search for signal" reports honestly when there is none', () async {
    final SeismikState state = build(() => 0);
    await state.onSignalChangedForTesting(false);

    expect(await state.retryConnection(), isFalse);
    expect(state.offlineEmergencyMode, isTrue);
    state.dispose();
  });
}
