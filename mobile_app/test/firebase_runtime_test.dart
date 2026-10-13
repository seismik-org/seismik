import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/firebase_runtime.dart';

void main() {
  test(
    'concurrent registration and notification startup share one gate',
    () async {
      final gate = Completer<void>();
      var starts = 0;
      final runtime = ServiceReadiness(() async {
        starts++;
        await gate.future;
      });
      final first = runtime.ensureReady();
      final second = runtime.ensureReady();
      expect(identical(first, second), isTrue);
      expect(starts, 1);
      gate.complete();
      await Future.wait([first, second]);
      await runtime.ensureReady();
      expect(starts, 1);
    },
  );
  test(
    'failed SDK initialization is not mistaken for readiness and retries',
    () async {
      var starts = 0;
      final runtime = ServiceReadiness(() async {
        if (++starts == 1) {
          throw StateError('Firebase configuration unavailable');
        }
      });
      await expectLater(runtime.ensureReady(), throwsStateError);
      await runtime.ensureReady();
      expect(starts, 2);
    },
  );
}
