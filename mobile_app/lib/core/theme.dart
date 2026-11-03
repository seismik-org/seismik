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
  static const Color fallbackSeed = Color(0xFF087F8C);

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

  static ColorScheme scheme({required Brightness brightness}) {
    final dark = brightness == Brightness.dark;
    return ColorScheme.fromSeed(
      seedColor: fallbackSeed,
      brightness: brightness,
      dynamicSchemeVariant: DynamicSchemeVariant.tonalSpot,
    ).copyWith(
      primary: dark ? const Color(0xFF73D5ED) : const Color(0xFF006D85),
      onPrimary: dark ? const Color(0xFF003543) : Colors.white,
      primaryContainer: dark
          ? const Color(0xFF123E4A)
          : const Color(0xFFCDF0FA),
      onPrimaryContainer: dark
          ? const Color(0xFFC5EFF9)
          : const Color(0xFF00323D),
      surface: dark ? const Color(0xFF101820) : const Color(0xFFF5F8FC),
      surfaceContainer: dark
          ? const Color(0xFF17222E)
          : const Color(0xFFEDF3F8),
      surfaceContainerHighest: dark
          ? const Color(0xFF263747)
          : const Color(0xFFDEE8F1),
      onSurface: dark ? const Color(0xFFE4EDF5) : const Color(0xFF162736),
      onSurfaceVariant: dark
          ? const Color(0xFFB4C5D5)
          : const Color(0xFF455A6B),
    );
  }

  /// Usa la variante que Android haya publicado para ese modo concreto.
  ///
  /// Algunos fabricantes exponen primero (o solamente) una de las dos
  /// variantes Monet. Exigir luz *y* oscuridad hacía que Seismik descartara
  /// una paleta válida y volviera al azul de respaldo, aunque las demás apps
  /// sí usaran Material You.
  static ColorScheme platformScheme({
    required ColorScheme? dynamicScheme,
    required Brightness brightness,
  }) => dynamicScheme ?? scheme(brightness: brightness);
}
