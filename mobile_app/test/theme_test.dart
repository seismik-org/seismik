import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/theme.dart';

void main() {
  test('fallback supports light and dark system modes', () {
    final ThemeData light = SeismikTheme.fromScheme(
      SeismikTheme.scheme(brightness: Brightness.light),
    );
    final ThemeData dark = SeismikTheme.fromScheme(
      SeismikTheme.scheme(brightness: Brightness.dark),
    );

    expect(light.useMaterial3, isTrue);
    expect(light.brightness, Brightness.light);
    expect(dark.brightness, Brightness.dark);
    expect(light.colorScheme.primary, isNot(dark.colorScheme.primary));
  });

  test('uses the exact Android Material You accent without substitution', () {
    const Color samsungAccent = Color(0xFF8D6E63);
    final ColorScheme light = SeismikTheme.scheme(
      brightness: Brightness.light,
      exactSystemAccent: samsungAccent,
    );
    final ColorScheme dark = SeismikTheme.scheme(
      brightness: Brightness.dark,
      exactSystemAccent: samsungAccent,
    );

    expect(light.primary, samsungAccent);
    expect(dark.primary, samsungAccent);
  });
}
