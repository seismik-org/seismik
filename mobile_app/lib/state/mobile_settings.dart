import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MobileSettings extends ChangeNotifier {
  static const String _themeKey = 'settings.theme_mode';
  static const String _dynamicColorKey = 'settings.dynamic_color';
  static const String _crowdsourcingKey = 'settings.crowdsourcing';
  static const String _preciseLocationKey = 'settings.precise_location';
  static const String _minimumMagnitudeKey = 'settings.minimum_magnitude';
  static const String _historyDaysKey = 'settings.history_days';
  static const String _historySourcesKey = 'settings.history_sources';
  static const String _earlyAlertsKey = 'settings.early_alerts';
  static const String _officialUpdatesKey = 'settings.official_updates';
  static const String _notificationMagnitudeKey =
      'settings.notification_magnitude';

  ThemeMode themeMode = ThemeMode.system;
  bool useDynamicColor = true;
  bool crowdsourcingEnabled = true;
  bool preciseLocationByDefault = false;
  double minimumHistoryMagnitude = 2.5;
  int historyDays = 7;
  Set<String> historySources = <String>{'sgc_colombia', 'usgs_global'};
  bool receiveEarlyAlerts = true;
  bool receiveOfficialUpdates = true;
  double minimumNotificationMagnitude = 4.0;

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
    }
    receiveEarlyAlerts = preferences.getBool(_earlyAlertsKey) ?? true;
    receiveOfficialUpdates = preferences.getBool(_officialUpdatesKey) ?? true;
    minimumNotificationMagnitude =
        preferences.getDouble(_notificationMagnitudeKey) ?? 4.0;
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
    receiveEarlyAlerts = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_earlyAlertsKey, value);
  }

  Future<void> setReceiveOfficialUpdates(bool value) async {
    receiveOfficialUpdates = value;
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_officialUpdatesKey, value);
  }

  Future<void> setMinimumNotificationMagnitude(double value) async {
    minimumNotificationMagnitude = value.clamp(0, 9).toDouble();
    notifyListeners();
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.setDouble(
      _notificationMagnitudeKey,
      minimumNotificationMagnitude,
    );
  }
}
