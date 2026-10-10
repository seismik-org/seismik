import 'dart:math' as math;

import '../core/constants.dart';

/// Experimental summary, NOT a classifier of earthquakes or P waves.
class MotionEvidence {
  const MotionEvidence({
    required this.at,
    required this.peakG,
    required this.rmsG,
    required this.durationMs,
    required this.samples,
    required this.thresholdSamples,
    required this.samplingHz,
    required this.maxGapMs,
    required this.stationarySeconds,
  });
  final DateTime at;
  final double peakG, rmsG, durationMs, samplingHz, maxGapMs, stationarySeconds;
  final int samples, thresholdSamples;
}

class MotionEvidenceDetector {
  DateTime? _last, _quietSince, _onset;
  double _peak = 0, _squares = 0, _gap = 0;
  double _intervalTotalMs = 0, _cadenceGap = 0;
  int _intervalCount = 0;
  int _count = 0, _above = 0;
  double _stationary = 0;
  DateTime? _cooldownUntil;

  double get stationarySeconds => _stationary;
  bool get available => _stationary >= 30 && _onset == null;
  double get samplingHz =>
      _intervalTotalMs > 0 ? 1000 * _intervalCount / _intervalTotalMs : 0;
  double get maxGapMs => _cadenceGap;

  void reset() {
    _last = _quietSince = _onset = _cooldownUntil = null;
    _stationary = _peak = _squares = _gap = _intervalTotalMs = _cadenceGap = 0;
    _intervalCount = 0;
    _count = _above = 0;
  }

  MotionEvidence? add(DateTime at, double x, double y, double z) {
    if (![x, y, z].every((v) => v.isFinite)) {
      reset();
      return null;
    }
    final previous = _last;
    final dt = previous == null
        ? 0.0
        : at.difference(previous).inMicroseconds / 1000;
    if (previous != null && (dt <= 0 || dt > 100)) {
      reset();
      _last = at;
      return null;
    }
    _last = at;
    if (dt > 0) {
      _intervalTotalMs += dt;
      _intervalCount++;
      _cadenceGap = math.max(_cadenceGap, dt);
    }
    final magnitude = math.sqrt(x * x + y * y + z * z);
    final threshold = SeismikConstants.shakeThresholdMetersPerSecondSquared;
    if (_onset == null) {
      if (magnitude < .12) {
        _quietSince ??= at;
        _stationary = at.difference(_quietSince!).inMilliseconds / 1000;
        return null;
      }
      if (_cooldownUntil != null && at.isBefore(_cooldownUntil!)) return null;
      if (_stationary < 30 || magnitude < threshold) {
        _quietSince = null;
        _stationary = 0;
        return null;
      }
      _onset = at;
      _count = _above = 0;
      _peak = _squares = _gap = 0;
    }
    _count++;
    if (magnitude >= threshold) _above++;
    _peak = math.max(_peak, magnitude);
    _squares += magnitude * magnitude;
    _gap = math.max(_gap, dt);
    final duration = at.difference(_onset!).inMilliseconds.toDouble();
    if (duration < 200) return null;
    // A single knock does not become a report just because the phone was quiet.
    final evidence = _above >= 3 && _count >= 5 && duration <= 2000
        ? MotionEvidence(
            at: at,
            peakG: _peak / SeismikConstants.gravity,
            rmsG: math.sqrt(_squares / _count) / SeismikConstants.gravity,
            durationMs: duration,
            samples: _count,
            thresholdSamples: _above,
            samplingHz: (_count - 1) / (duration / 1000),
            maxGapMs: _gap,
            stationarySeconds: _stationary,
          )
        : null;
    _onset = _quietSince = null;
    _stationary = 0;
    _cooldownUntil = at.add(const Duration(seconds: 8));
    return evidence;
  }
}
