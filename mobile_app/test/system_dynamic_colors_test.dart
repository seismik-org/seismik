import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/system_dynamic_colors.dart';

void main() {
  Map<String, int> roles() => {
    'primary': 0xff123456,
    'on_primary': 0xffffffff,
    'secondary': 0xff334455,
    'on_secondary': 0xffffffff,
    'tertiary': 0xff665544,
    'surface': 0xff101010,
    'on_surface': 0xffeeeeee,
    'error': 0xffbb0000,
    'on_error': 0xffffffff,
    'surface_container': 0xff181818,
    'surface_container_highest': 0xff282828,
    'primary_container': 0xff223344,
  };

  test(
    'preserves resolved system colors exactly instead of seeding a palette',
    () {
      for (final mode in Brightness.values) {
        final scheme = SystemDynamicColorBuilder.scheme(roles(), mode)!;
        expect(scheme.primary.toARGB32(), 0xff123456);
        expect(scheme.secondary.toARGB32(), 0xff334455);
        expect(scheme.tertiary.toARGB32(), 0xff665544);
        expect(scheme.surfaceContainer.toARGB32(), 0xff181818);
        expect(scheme.surfaceContainerHighest.toARGB32(), 0xff282828);
        expect(scheme.brightness, mode);
      }
    },
  );

  test('missing or malformed native data falls back without a crash', () {
    expect(SystemDynamicColorBuilder.scheme(null, Brightness.light), isNull);
    final incomplete = roles()..remove('error');
    expect(
      SystemDynamicColorBuilder.scheme(incomplete, Brightness.light),
      isNull,
    );
    expect(
      SystemDynamicColorBuilder.scheme({'primary': 'blue'}, Brightness.dark),
      isNull,
    );
  });
}
