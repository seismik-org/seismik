import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/constants.dart';
import 'package:seismik/services/accelerometer_service.dart';

/// Referencia deliberadamente ingenua: recorre toda la ventana, como hacía el
/// servicio antes de usar sumas acumuladas.
double referenceVariance(List<double> values) {
  if (values.length < MotionWindow.minimumSamples) return double.infinity;
  final double mean = values.reduce((a, b) => a + b) / values.length;
  return values
          .map((value) => math.pow(value - mean, 2).toDouble())
          .reduce((a, b) => a + b) /
      values.length;
}

void main() {
  test('la varianza acumulada coincide con recorrer la ventana', () {
    final math.Random random = math.Random(20260912);
    final MotionWindow window = MotionWindow();
    final List<(DateTime, double)> reference = <(DateTime, double)>[];
    DateTime now = DateTime.utc(2026, 9, 12);

    for (int i = 0; i < 12000; i++) {
      if (i % 53 == 0) {
        final double expected = referenceVariance(
          reference.map((sample) => sample.$2).toList(growable: false),
        );
        if (expected.isInfinite) {
          expect(window.variance, double.infinity);
        } else {
          expect(window.variance, closeTo(expected, 1e-9));
        }
      }
      // Entre 40 y 250 muestras por segundo, como sensores de teléfonos
      // distintos: a veces la ventana se llena por cantidad y no por tiempo.
      now = now.add(Duration(microseconds: 4000 + random.nextInt(21000)));
      final double magnitude = random.nextDouble() * (i.isEven ? 0.05 : 0.8);
      window.add(now, magnitude);

      reference.add((now, magnitude));
      final DateTime cutoff = now.subtract(SeismikConstants.dspWindow);
      reference.removeWhere((sample) => sample.$1.isBefore(cutoff));
      if (reference.length > SeismikConstants.dspMaximumSamples) {
        reference.removeRange(
          0,
          reference.length - SeismikConstants.dspMaximumSamples,
        );
      }
      expect(window.length, reference.length);
    }
  });

  test('con pocas muestras no hay referencia y la varianza es infinita', () {
    final MotionWindow window = MotionWindow();
    final DateTime start = DateTime.utc(2026);
    for (int i = 0; i < MotionWindow.minimumSamples - 1; i++) {
      window.add(start.add(Duration(milliseconds: 20 * i)), 0.01);
    }
    expect(window.variance, double.infinity);

    window.add(start.add(const Duration(milliseconds: 240)), 0.01);
    expect(window.variance, closeTo(0, 1e-12));
  });

  test('un sensor muy rápido no hace crecer la ventana sin límite', () {
    final MotionWindow window = MotionWindow();
    final DateTime start = DateTime.utc(2026);
    for (int i = 0; i < 2000; i++) {
      window.add(start.add(Duration(milliseconds: i)), 0.02);
    }
    expect(window.length, SeismikConstants.dspMaximumSamples);
  });

  test('clear descarta las muestras y sus sumas', () {
    final MotionWindow window = MotionWindow();
    final DateTime start = DateTime.utc(2026);
    for (int i = 0; i < 50; i++) {
      window.add(start.add(Duration(milliseconds: 20 * i)), i.isEven ? 0.9 : 0);
    }
    window.clear();
    expect(window.length, 0);

    for (int i = 0; i < 20; i++) {
      window.add(start.add(Duration(seconds: 10, milliseconds: 20 * i)), 0.3);
    }
    expect(window.variance, closeTo(0, 1e-12));
  });
}
