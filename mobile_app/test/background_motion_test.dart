import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seismik/services/accelerometer_service.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/background_motion_service.dart';
import 'package:seismik/state/mobile_settings.dart';

class RecordingApi extends ApiClient {
  int attempts = 0;
  bool fail = false;
  @override
  Future<void> sendShake({
    required double latitude,
    required double longitude,
    required double pgaG,
    required int timestampMilliseconds,
  }) async {
    attempts++;
    if (fail) throw StateError('offline');
  }
}

Position fix({double accuracy = 10, Duration age = Duration.zero}) => Position(
  latitude: 4.6,
  longitude: -74.1,
  timestamp: DateTime.now().subtract(age),
  accuracy: accuracy,
  altitude: 0,
  altitudeAccuracy: 0,
  heading: 0,
  headingAccuracy: 0,
  speed: 0,
  speedAccuracy: 0,
);

void prime(StreamController<UserAccelerometerEvent> stream) {
  for (int i = 0; i < 12; i++) {
    stream.add(UserAccelerometerEvent(0, 0, 0, DateTime.now()));
  }
  stream.add(UserAccelerometerEvent(1, 0, 0, DateTime.now()));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'background is opt-in and notification stop reloads across isolates',
    () async {
      SharedPreferences.setMockInitialValues({});
      final settings = MobileSettings();
      await settings.load();
      expect(settings.backgroundCrowdsourcingEnabled, false);
      await settings.setBackgroundCrowdsourcingEnabled(true);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(MobileSettings.backgroundCrowdsourcingKey, false);
      await settings.reloadBackgroundCrowdsourcing();
      expect(settings.backgroundCrowdsourcingEnabled, false);
    },
  );
  test('rejects stale and inaccurate locations', () {
    expect(usableMotionLocation(fix()), true);
    expect(usableMotionLocation(fix(accuracy: 501)), false);
    expect(usableMotionLocation(fix(age: const Duration(minutes: 3))), false);
    expect(usableMotionLocation(fix(accuracy: double.nan)), false);
  });
  test(
    'quiet baseline and spike sends authenticated summary only once',
    () async {
      final stream = StreamController<UserAccelerometerEvent>();
      final api = RecordingApi();
      final sensor = AccelerometerService(
        apiClient: api,
        samples: stream.stream,
        chargingProvider: () async => false,
        positionProvider: () async => (latitude: 4.6, longitude: -74.1),
      );
      await sensor.start();
      prime(stream);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(api.attempts, 1);
      expect(sensor.reportsSent, 1);
      await sensor.stop();
      await stream.close();
      api.close();
    },
  );
  test('stop while awaiting location prevents a late send', () async {
    final stream = StreamController<UserAccelerometerEvent>();
    final api = RecordingApi();
    final position = Completer<({double latitude, double longitude})?>();
    final sensor = AccelerometerService(
      apiClient: api,
      samples: stream.stream,
      chargingProvider: () async => false,
      positionProvider: () => position.future,
    );
    await sensor.start();
    prime(stream);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await sensor.stop();
    position.complete((latitude: 4.6, longitude: -74.1));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(api.attempts, 0);
    await stream.close();
    api.close();
  });
  test(
    'network failure backs off instead of retrying at sensor frequency',
    () async {
      final stream = StreamController<UserAccelerometerEvent>();
      final api = RecordingApi()..fail = true;
      final sensor = AccelerometerService(
        apiClient: api,
        samples: stream.stream,
        chargingProvider: () async => false,
        positionProvider: () async => (latitude: 4.6, longitude: -74.1),
      );
      await sensor.start();
      prime(stream);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      prime(stream);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(api.attempts, 1);
      expect(sensor.lastError, isNotNull);
      await sensor.stop();
      await stream.close();
      api.close();
    },
  );
}
