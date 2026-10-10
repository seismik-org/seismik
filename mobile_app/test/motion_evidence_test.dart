import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/motion_evidence.dart';

DateTime baseline(MotionEvidenceDetector detector, {int interval = 20}) {
  var at = DateTime.utc(2026);
  for (int i = 0; i <= 31000 ~/ interval; i++) {
    detector.add(at, .01, .01, .01);
    at = at.add(Duration(milliseconds: interval));
  }
  return at;
}

void main() {
  test('sustained shaking requires a quiet 30 second baseline', () {
    final detector = MotionEvidenceDetector();
    var at = DateTime.utc(2026);
    for (int i = 0; i < 50; i++) {
      expect(detector.add(at, .8, 0, 0), isNull);
      at = at.add(const Duration(milliseconds: 20));
    }
    at = baseline(detector);
    expect(detector.available, true);
    expect(detector.samplingHz, closeTo(50, .1));
    MotionEvidence? evidence;
    for (int i = 0; i < 11; i++) {
      evidence = detector.add(at, i.isEven ? .8 : -.8, 0, 0) ?? evidence;
      at = at.add(const Duration(milliseconds: 20));
    }
    expect(evidence, isNotNull);
    expect(evidence!.thresholdSamples, 11);
    expect(evidence.durationMs, 200);
    expect(evidence.stationarySeconds, greaterThanOrEqualTo(30));
  });
  test('an isolated knock does not become an earthquake report', () {
    final detector = MotionEvidenceDetector();
    var at = baseline(detector);
    expect(detector.add(at, 2, 0, 0), isNull);
    for (int i = 0; i < 20; i++) {
      at = at.add(const Duration(milliseconds: 20));
      expect(detector.add(at, .01, 0, 0), isNull);
    }
  });
  test('sampling gap and nonfinite data reset availability', () {
    final detector = MotionEvidenceDetector();
    final at = baseline(detector);
    expect(detector.available, true);
    expect(detector.add(at.add(const Duration(seconds: 2)), .8, 0, 0), isNull);
    expect(detector.available, false);
    baseline(detector);
    expect(detector.add(at, double.nan, 0, 0), isNull);
    expect(detector.available, false);
  });
  test('a report is followed by cooldown and a new stationary baseline', () {
    final detector = MotionEvidenceDetector();
    var at = baseline(detector);
    var reports = 0;
    for (int i = 0; i < 500; i++) {
      if (detector.add(at, .8, 0, 0) != null) reports++;
      at = at.add(const Duration(milliseconds: 20));
    }
    expect(reports, 1);
  });
}
