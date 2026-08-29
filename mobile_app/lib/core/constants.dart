import 'package:flutter/foundation.dart';

abstract final class SeismikConstants {
  static const String appName = 'Seismik';
  static const String apiBaseUrl = String.fromEnvironment(
    'SEISMIK_API_BASE_URL',
    defaultValue: 'https://api.seismik.example',
  );
  static const String deviceApiKey = String.fromEnvironment(
    'SEISMIK_DEVICE_KEY',
  );
  static const String criticalChannelId = 'seismic_critical_alerts';
  static const String updatesChannelId = 'seismic_updates';
  static const double gravity = 9.80665;
  static const double shakeThresholdMetersPerSecondSquared = 0.04 * gravity;
  static const Duration shakeCooldown = Duration(seconds: 3);
  static const Duration dspWindow = Duration(milliseconds: 2500);
  static const int dspMaximumSamples = 160;
  static const double userMotionVarianceThreshold = 0.12;
  static void validateBuildConfiguration() {
    if (kReleaseMode &&
        (deviceApiKey.isEmpty || apiBaseUrl.contains('.example'))) {
      throw StateError(
        'Release requires SEISMIK_API_BASE_URL and SEISMIK_DEVICE_KEY.',
      );
    }
  }
}
