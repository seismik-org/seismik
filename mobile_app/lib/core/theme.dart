import 'package:flutter/material.dart';

abstract final class SeismikColors {
  // Base backgrounds
  static const Color obsidian = Color(0xFF0B0E14);
  static const Color obsidianElevated = Color(0xFF141A24);
  
  // Apple HIG System Accents
  static const Color systemBlue = Color(0xFF007AFF);
  static const Color emerald = Color(0xFF30D158);
  static const Color amber = Color(0xFFFF9F0A);
  static const Color crimson = Color(0xFFFF453A);
  static const Color glacier = Color(0xFF32ADE6);
  static const Color lavender = Color(0xFFBF5AF2);

  /// Devuelve el color semántico según la severidad del sismo.
  static Color severityColor(double? magnitude, {bool isPreliminary = false}) {
    if (isPreliminary) return lavender;
    if (magnitude == null) return systemBlue;
    if (magnitude < 4.0) return glacier;
    if (magnitude < 5.5) return amber;
    return crimson;
  }

  /// Gradiente especular suave para badges de cristal.
  static LinearGradient severityGradient(
    double? magnitude, {
    bool isPreliminary = false,
  }) {
    final Color base = severityColor(magnitude, isPreliminary: isPreliminary);
    return LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: <Color>[
        base.withValues(alpha: 0.95),
        base.withValues(alpha: 0.70),
      ],
    );
  }
}

abstract final class SeismikTheme {
  static const Color fallbackSeed = Color(0xFF1B55B8);

  static ThemeData fromScheme(ColorScheme scheme) => ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    brightness: scheme.brightness,
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      centerTitle: false,
      scrolledUnderElevation: 0,
    ),
    cardTheme: CardThemeData(
      color: scheme.surfaceContainer,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(20),
        borderSide: BorderSide.none,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainer,
      indicatorColor: scheme.primaryContainer,
      indicatorShape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(28),
      ),
      labelTextStyle: WidgetStatePropertyAll(
        TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: scheme.inverseSurface,
      contentTextStyle: TextStyle(color: scheme.onInverseSurface),
    ),
  );

  static ColorScheme scheme({required Brightness brightness}) =>
      ColorScheme.fromSeed(
        seedColor: fallbackSeed,
        brightness: brightness,
        dynamicSchemeVariant: DynamicSchemeVariant.fidelity,
      );
}

