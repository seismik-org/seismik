import 'dart:io';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/map_launcher.dart';

class MobileSettings extends ChangeNotifier {
  static const String _themeKey = 'settings.theme_mode';
  static const String _dynamicColorKey = 'settings.dynamic_color';
  static const String _crowdsourcingKey = 'settings.crowdsourcing';
  static const String _preciseLocationKey = 'settings.precise_location';
  static const String _minimumMagnitudeKey = 'settings.minimum_magnitude';
  static const String _historyDaysKey = 'settings.history_days';
  static const String _historySourcesKey = 'settings.history_sources';
  static const String _preliminaryHistoryMigratedKey =
      'settings.preliminary_history_migrated';
  static const String _earlyAlertsKey = 'settings.early_alerts';
  static const String _officialUpdatesKey = 'settings.official_updates';
  static const String _notificationMagnitudeKey =
      'settings.notification_magnitude';
  static const String _alertRadiusKey = 'settings.alert_radius_km';
  static const String _mapProviderKey = 'settings.map_provider';

  /// Radios ofrecidos para el umbral de cercanía de las alertas.
  static const List<double> alertRadiusOptions = <double>[
    50,
    100,
    150,
    250,
    400,
    600,
  ];

  ThemeMode themeMode = ThemeMode.system;
  bool useDynamicColor = true;
  bool crowdsourcingEnabled = true;
  bool preciseLocationByDefault = false;
  double minimumHistoryMagnitude = 2.5;
  int historyDays = 7;
  Set<String> historySources = <String>{
    'sgc_colombia',
    'usgs_global',
    'seismik_seedlink_preliminary',
  };
  bool receiveEarlyAlerts = true;
  bool receiveOfficialUpdates = true;
  double minimumNotificationMagnitude = 4.0;
  double alertRadiusKm = 250.0;
  MapProvider mapProvider = MapProvider.system;

  Future<void> load() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    themeMode = switch (preferences.getString(_themeKey)) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };
    useDynamicColor = preferences.getBool(_dynamicColorKey) ?? true;
    crowdsourcingEnabled = preferences.getBool(_crowdsourcingKey) ?? true;
    preciseLocationByDefault =
        preferences.getBool(_preciseLocationKey) ?? false;
    minimumHistoryMagnitude =
        preferences.getDouble(_minimumMagnitudeKey) ?? 2.5;
    historyDays = preferences.getInt(_historyDaysKey) ?? 7;
    final List<String>? sources = preferences.getStringList(_historySourcesKey);
    if (sources != null && sources.isNotEmpty) {
      historySources = sources.toSet();
      // Se incorpora una sola vez a instalaciones existentes. Luego la
      // persona conserva el control: al desactivarla no reaparece al reiniciar.
      if (!(preferences.getBool(_preliminaryHistoryMigratedKey) ?? false)) {
        historySources.add('seismik_seedlink_preliminary');
        await preferences.setBool(_preliminaryHistoryMigratedKey, true);
      }
    }
    receiveEarlyAlerts = preferences.getBool(_earlyAlertsKey) ?? true;
    receiveOfficialUpdates = preferences.getBool(_officialUpdatesKey) ?? true;
    minimumNotificationMagnitude =
        preferences.getDouble(_notificationMagnitudeKey) ?? 4.0;
    alertRadiusKm = _normalizeRadius(preferences.getDouble(_alertRadiusKey));
    final String? savedMapProvider = preferences.getString(_mapProviderKey);
    // Apple Maps is a real native choice on a fresh iPhone installation.  It
    // must not inherit Android's generic browser/system fallback.
    mapProvider = savedMapProvider == null && Platform.isIOS
        ? MapProvider.apple
        : MapProvider.fromName(savedMapProvider);
  }

  /// Los umbrales fuera de rango del servidor se ajustan al valor admitido más
  /// cercano en lugar de rechazar el registro del dispositivo.
  static double _normalizeRadius(double? value) {
    if (value == null) return 250.0;
    return value.clamp(10, 2000).toDouble();
  }

  Future<void> setThemeMode(ThemeMode value) async {
    if (themeMode == value) return;
    themeMode = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_themeKey, value.name);
  }

  Future<void> setUseDynamicColor(bool value) async {
    if (useDynamicColor == value) return;
    useDynamicColor = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_dynamicColorKey, value);
  }

  Future<void> setCrowdsourcingEnabled(bool value) async {
    if (crowdsourcingEnabled == value) return;
    crowdsourcingEnabled = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_crowdsourcingKey, value);
  }

  Future<void> setPreciseLocationByDefault(bool value) async {
    if (preciseLocationByDefault == value) return;
    preciseLocationByDefault = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_preciseLocationKey, value);
  }

  Future<void> setMinimumHistoryMagnitude(double value) async {
    final double normalized = value.clamp(0, 8).toDouble();
    if (minimumHistoryMagnitude == normalized) return;
    minimumHistoryMagnitude = normalized;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setDouble(_minimumMagnitudeKey, normalized);
  }

  Future<void> setHistoryDays(int value) async {
    final int normalized = value.clamp(1, 30);
    if (historyDays == normalized) return;
    historyDays = normalized;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setInt(_historyDaysKey, normalized);
  }

  Future<void> setHistorySource(String sourceId, bool enabled) async {
    final Set<String> next = Set<String>.of(historySources);
    enabled ? next.add(sourceId) : next.remove(sourceId);
    if (next.isEmpty ||
        next.length == historySources.length &&
            next.containsAll(historySources)) {
      return;
    }
    historySources = next;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setStringList(
      _historySourcesKey,
      historySources.toList()..sort(),
    );
  }

  Future<void> setReceiveEarlyAlerts(bool value) async {
    if (receiveEarlyAlerts == value) return;
    receiveEarlyAlerts = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_earlyAlertsKey, value);
  }

  Future<void> setReceiveOfficialUpdates(bool value) async {
    if (receiveOfficialUpdates == value) return;
    receiveOfficialUpdates = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_officialUpdatesKey, value);
  }

  Future<void> setMinimumNotificationMagnitude(double value) async {
    final double normalized = value.clamp(0, 9).toDouble();
    if (minimumNotificationMagnitude == normalized) return;
    minimumNotificationMagnitude = normalized;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setDouble(
      _notificationMagnitudeKey,
      minimumNotificationMagnitude,
    );
  }

  /// Umbral de cercanía: sólo llegan avisos con epicentro dentro de este radio.
  Future<void> setAlertRadiusKm(double value) async {
    final double normalized = _normalizeRadius(value);
    if (alertRadiusKm == normalized) return;
    alertRadiusKm = normalized;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setDouble(_alertRadiusKey, normalized);
  }

  Future<void> setMapProvider(MapProvider value) async {
    if (mapProvider == value) return;
    mapProvider = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setString(_mapProviderKey, value.name);
  }
}
