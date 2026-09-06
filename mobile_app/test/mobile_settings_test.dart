import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/map_launcher.dart';
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

  test(
    'preliminary SeedLink source is added to existing installations',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'settings.history_sources': <String>['sgc_colombia'],
      });
      final MobileSettings settings = MobileSettings();
      await settings.load();

      expect(settings.historySources, contains('seismik_seedlink_preliminary'));

      await settings.setHistorySource('sgc_colombia', false);

      expect(settings.historySources, <String>{'seismik_seedlink_preliminary'});
    },
  );

  test('el umbral de alerta y el proveedor de mapas persisten', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final MobileSettings settings = MobileSettings();
    await settings.load();
    expect(settings.alertRadiusKm, 250.0);
    expect(settings.mapProvider, MapProvider.system);

    await settings.setAlertRadiusKm(100);
    await settings.setMinimumNotificationMagnitude(5.5);
    await settings.setMapProvider(MapProvider.apple);

    final MobileSettings restored = MobileSettings();
    await restored.load();
    expect(restored.alertRadiusKm, 100.0);
    expect(restored.minimumNotificationMagnitude, 5.5);
    expect(restored.mapProvider, MapProvider.apple);
  });

  test('un umbral fuera de rango se ajusta al límite admitido', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final MobileSettings settings = MobileSettings();
    await settings.load();

    await settings.setAlertRadiusKm(9999);
    expect(settings.alertRadiusKm, 2000.0);

    await settings.setAlertRadiusKm(1);
    expect(settings.alertRadiusKm, 10.0);
  });

  test('un radio guardado inválido no bloquea el arranque', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'settings.alert_radius_km': 100000.0,
    });
    final MobileSettings settings = MobileSettings();
    await settings.load();

    expect(settings.alertRadiusKm, 2000.0);
  });

  test('cada radio ofrecido es aceptado sin ajuste', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final MobileSettings settings = MobileSettings();
    await settings.load();

    for (final double radius in MobileSettings.alertRadiusOptions) {
      await settings.setAlertRadiusKm(radius);
      expect(settings.alertRadiusKm, radius);
    }
  });
}
