import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/system_theme.dart';
import 'package:seismik_wear/theme.dart';

void main() {
  test('unsupported and incomplete watch roles use Seismik fallback', () {
    expect(WatchSystemTheme.resolve(null).primary, wearPrimary);
    expect(
      WatchSystemTheme.resolve({'primary': 0xFFFF0000}).primary,
      wearPrimary,
    );
  });
  test('resolved watch color roles are preserved without recoloring', () {
    final scheme = WatchSystemTheme.resolve({
      'primary': 0xFF99FF88,
      'on_primary': 0xFF123400,
      'surface': 0xFF000000,
      'on_surface': 0xFFF2FFE1,
      'surface_container': 0xFF172419,
      'on_surface_variant': 0xFFAABB99,
    });
    expect(scheme.primary, const Color(0xFF99FF88));
    expect(scheme.onPrimary, const Color(0xFF123400));
    expect(scheme.surfaceContainer, const Color(0xFF172419));
    expect(scheme.brightness, Brightness.dark);
  });
}
