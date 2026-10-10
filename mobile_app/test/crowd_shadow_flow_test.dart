import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:seismik/services/accelerometer_service.dart';
import 'package:seismik/services/api_client.dart';

class ShadowApi extends ApiClient {
  final summaries = <Map<String, dynamic>>[];
  int legacyCalls = 0;
  @override
  Future<void> sendCrowdShadow(
    Map<String, dynamic> summary, {
    required bool presence,
  }) async {
    summaries.add({...summary, 'presence': presence});
  }

  @override
  Future<void> sendShake({
    required double latitude,
    required double longitude,
    required double pgaG,
    required int timestampMilliseconds,
  }) async {
    legacyCalls++;
  }
}

void samples(
  StreamController<UserAccelerometerEvent> stream, {
  bool sustained = true,
}) {
  var at = DateTime.now().subtract(const Duration(seconds: 31));
  for (int i = 0; i < 1550; i++) {
    stream.add(UserAccelerometerEvent(.01, 0, 0, at));
    at = at.add(const Duration(milliseconds: 20));
  }
  for (int i = 0; i < 11; i++) {
    stream.add(
      UserAccelerometerEvent(sustained || i == 0 ? .8 : .01, 0, 0, at),
    );
    at = at.add(const Duration(milliseconds: 20));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final caseName in ['valid', 'knock', 'missing_accuracy', 'stop']) {
    test('experimental flow: $caseName never falls back to legacy', () async {
      final api = ShadowApi();
      final stream = StreamController<UserAccelerometerEvent>();
      final location = Completer<({double latitude, double longitude})?>();
      final sensor = AccelerometerService(
        apiClient: api,
        samples: stream.stream,
        experimentalShadow: true,
        chargingProvider: () async => false,
        locationAccuracyProvider: () =>
            caseName == 'missing_accuracy' ? null : 10,
        positionProvider: () => caseName == 'stop'
            ? location.future
            : Future.value((latitude: 4.65, longitude: -74.05)),
      );
      await sensor.start();
      samples(stream, sustained: caseName != 'knock');
      await Future<void>.delayed(const Duration(milliseconds: 30));
      if (caseName == 'stop') {
        await sensor.stop();
        location.complete((latitude: 4.65, longitude: -74.05));
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      expect(api.legacyCalls, 0);
      expect(api.summaries.length, caseName == 'valid' ? 1 : 0);
      if (caseName == 'valid') {
        expect(
          api.summaries.single['stationary_seconds'],
          greaterThanOrEqualTo(30),
        );
        expect(api.summaries.single['duration_ms'], 200);
        expect(api.summaries.single['threshold_samples'], 11);
      }
      await sensor.stop();
      await stream.close();
      api.close();
    });
  }
}
