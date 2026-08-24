import 'dart:async';
import 'dart:math' as math;

import 'package:battery_plus/battery_plus.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../core/constants.dart';
import 'api_client.dart';

typedef PositionProvider =
    Future<({double latitude, double longitude})?> Function();

class AccelerometerService {
  AccelerometerService({
    required ApiClient apiClient,
    required PositionProvider positionProvider,
  }) : _apiClient = apiClient,
       _positionProvider = positionProvider;

  final ApiClient _apiClient;
  final PositionProvider _positionProvider;
  final Battery _battery = Battery();
  final List<_MagnitudeSample> _window = <_MagnitudeSample>[];
  StreamSubscription<UserAccelerometerEvent>? _subscription;
  DateTime _lastPing = DateTime.fromMillisecondsSinceEpoch(0);
  bool _sending = false;
  bool _charging = false;

  Future<void> start() async {
    if (_subscription != null) return;
    await _refreshBattery();
    _subscription =
        userAccelerometerEventStream(
          samplingPeriod: SensorInterval.gameInterval,
        ).listen(
          _onSample,
          onError: (_) {
            unawaited(stop());
          },
        );
  }

  void _onSample(UserAccelerometerEvent event) {
    final DateTime now = DateTime.now();
    final double magnitude = math.sqrt(
      event.x * event.x + event.y * event.y + event.z * event.z,
    );
    // La varianza se calcula sobre el historial anterior al pico. Incluir el
    // propio impulso haría que un sismo real pareciera movimiento del usuario.
    final double lowFrequencyVariance = _variance(
      _window.map((sample) => sample.magnitude).toList(growable: false),
    );
    _window.add(_MagnitudeSample(now, magnitude));
    final DateTime cutoff = now.subtract(SeismikConstants.dspWindow);
    _window.removeWhere((sample) => sample.at.isBefore(cutoff));
    if (_window.length > SeismikConstants.dspMaximumSamples) {
      _window.removeRange(
        0,
        _window.length - SeismikConstants.dspMaximumSamples,
      );
    }
    if (_window.length % 80 == 0) unawaited(_refreshBattery());

    final bool quietDevice =
        lowFrequencyVariance <= SeismikConstants.userMotionVarianceThreshold;
    final bool aboveThreshold =
        magnitude >= SeismikConstants.shakeThresholdMetersPerSecondSquared;
    final bool cooledDown =
        now.difference(_lastPing) >= SeismikConstants.shakeCooldown;
    final bool eligibleMotion =
        quietDevice ||
        (_charging &&
            lowFrequencyVariance <=
                SeismikConstants.userMotionVarianceThreshold * 2);
    if (!aboveThreshold || !eligibleMotion || !cooledDown || _sending) {
      return;
    }

    _sending = true;
    unawaited(_sendPing(now, magnitude));
  }

  Future<void> _sendPing(DateTime now, double magnitude) async {
    try {
      final ({double latitude, double longitude})? position =
          await _positionProvider();
      if (position == null) return;
      await _apiClient.sendShake(
        latitude: position.latitude,
        longitude: position.longitude,
        pgaG: magnitude / SeismikConstants.gravity,
        timestampMilliseconds: now.millisecondsSinceEpoch,
      );
      _lastPing = now;
    } finally {
      _sending = false;
    }
  }

  double _variance(List<double> values) {
    if (values.length < 12) return double.infinity;
    final double mean = values.reduce((a, b) => a + b) / values.length;
    return values
            .map((value) => math.pow(value - mean, 2).toDouble())
            .reduce((a, b) => a + b) /
        values.length;
  }

  Future<void> _refreshBattery() async {
    final BatteryState state = await _battery.batteryState;
    _charging = state == BatteryState.charging || state == BatteryState.full;
  }

  Future<void> stop() async {
    await _subscription?.cancel();
    _subscription = null;
    _window.clear();
  }
}

class _MagnitudeSample {
  const _MagnitudeSample(this.at, this.magnitude);
  final DateTime at;
  final double magnitude;
}
