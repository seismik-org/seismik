import 'package:flutter/material.dart';

abstract final class SeismikTheme {
  // Paleta de marca estable: evita que fabricantes sin Dynamic Color completo
  // sustituyan el diseño por el azul Material predeterminado de Google.
  static const Color oneUiIndigo = Color(0xFF4669A6);
  static const Color oneUiPeriwinkle = Color(0xFF8EA7D8);
  static const Color safetyCoral = Color(0xFFE6655E);

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

  static ColorScheme fallback(Brightness brightness) {
    final bool dark = brightness == Brightness.dark;
    return ColorScheme.fromSeed(
      seedColor: oneUiIndigo,
      brightness: brightness,
      dynamicSchemeVariant: DynamicSchemeVariant.fidelity,
    ).copyWith(
      primary: dark ? const Color(0xFFAFC6F2) : oneUiIndigo,
      onPrimary: dark ? const Color(0xFF142748) : Colors.white,
      primaryContainer: dark
          ? const Color(0xFF304A7A)
          : const Color(0xFFD9E4FF),
      onPrimaryContainer: dark
          ? const Color(0xFFE4ECFF)
          : const Color(0xFF142748),
      secondary: dark ? const Color(0xFFC2CBE0) : const Color(0xFF566176),
      tertiary: dark ? const Color(0xFFFFB4AE) : safetyCoral,
      surface: dark ? const Color(0xFF0B0D12) : const Color(0xFFF9F9FD),
      surfaceContainer: dark
          ? const Color(0xFF1B1D24)
          : const Color(0xFFEFEFF5),
      surfaceContainerHighest: dark
          ? const Color(0xFF303139)
          : const Color(0xFFE2E2EA),
    );
  }
}
