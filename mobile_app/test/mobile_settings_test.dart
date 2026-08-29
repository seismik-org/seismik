import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('settings persist and restore functional preferences', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final MobileSettings settings = MobileSettings();
    await settings.load();

    await settings.setThemeMode(ThemeMode.dark);
    await settings.setUseDynamicColor(false);
    await settings.setCrowdsourcingEnabled(false);
    await settings.setPreciseLocationByDefault(true);
    await settings.setMinimumHistoryMagnitude(4.5);
    await settings.setHistoryDays(14);
    await settings.setHistorySource('igp_peru', true);

    final MobileSettings restored = MobileSettings();
    await restored.load();
    expect(restored.themeMode, ThemeMode.dark);
    expect(restored.useDynamicColor, isFalse);
    expect(restored.crowdsourcingEnabled, isFalse);
    expect(restored.preciseLocationByDefault, isTrue);
    expect(restored.minimumHistoryMagnitude, 4.5);
    expect(restored.historyDays, 14);
    expect(restored.historySources, contains('igp_peru'));
  });

  test('at least one official history source remains selected', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'settings.history_sources': <String>['sgc_colombia'],
    });
    final MobileSettings settings = MobileSettings();
    await settings.load();

    await settings.setHistorySource('sgc_colombia', false);

    expect(settings.historySources, <String>{'sgc_colombia'});
  });
}
