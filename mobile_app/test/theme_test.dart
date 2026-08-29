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

  test('accepts the complete platform dynamic color scheme unchanged', () {
    final ColorScheme samsungScheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF8D6E63),
      brightness: Brightness.dark,
    );
    final ThemeData theme = SeismikTheme.fromScheme(samsungScheme);

    expect(theme.colorScheme, samsungScheme);
    expect(theme.colorScheme.primary, samsungScheme.primary);
    expect(theme.colorScheme.surface, samsungScheme.surface);
  });
}
