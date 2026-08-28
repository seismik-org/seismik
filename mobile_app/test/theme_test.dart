import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/theme.dart';

void main() {
  test('Material You fallback supports light and dark system modes', () {
    final ThemeData light = SeismikTheme.fromScheme(
      SeismikTheme.fallback(Brightness.light),
    );
    final ThemeData dark = SeismikTheme.fromScheme(
      SeismikTheme.fallback(Brightness.dark),
    );

    expect(light.useMaterial3, isTrue);
    expect(light.brightness, Brightness.light);
    expect(dark.brightness, Brightness.dark);
    expect(light.colorScheme.primary, isNot(dark.colorScheme.primary));
  });
}
