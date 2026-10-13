import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'theme.dart';

/// Use the watch's resolved roles, never the paired phone's accent palette.
class WatchSystemTheme extends StatefulWidget {
  const WatchSystemTheme({required this.builder, super.key});
  final Widget Function(ThemeData) builder;
  static const channel = MethodChannel('com.seismik.app/wear-colors');

  static ColorScheme resolve(Map<dynamic, dynamic>? roles) {
    const requiredRoles = <String>[
      'primary',
      'on_primary',
      'surface',
      'on_surface',
      'surface_container',
      'on_surface_variant',
    ];
    if (roles == null || requiredRoles.any((key) => roles[key] is! int)) {
      return const ColorScheme.dark(
        primary: wearPrimary,
        onPrimary: Color(0xFF00344F),
        surface: wearBackground,
        surfaceContainer: wearSurface,
        onSurface: Color(0xFFF0F3F8),
        onSurfaceVariant: wearMuted,
      );
    }
    return ColorScheme.dark(
      primary: Color(roles['primary'] as int),
      onPrimary: Color(roles['on_primary'] as int),
      surface: Color(roles['surface'] as int),
      onSurface: Color(roles['on_surface'] as int),
      surfaceContainer: Color(roles['surface_container'] as int),
      onSurfaceVariant: Color(roles['on_surface_variant'] as int),
    );
  }

  @override
  State<WatchSystemTheme> createState() => _WatchSystemThemeState();
}

class _WatchSystemThemeState extends State<WatchSystemTheme>
    with WidgetsBindingObserver {
  ColorScheme _scheme = WatchSystemTheme.resolve(null);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    try {
      final roles = await WatchSystemTheme.channel
          .invokeMapMethod<String, dynamic>('getColors');
      if (mounted) setState(() => _scheme = WatchSystemTheme.resolve(roles));
    } on PlatformException {
      // Unsupported watch: keep the accessible Seismik fallback.
    } on MissingPluginException {
      // Tests and platforms without Wear dynamic roles use the same fallback.
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(
    ThemeData(
      useMaterial3: true,
      colorScheme: _scheme,
      scaffoldBackgroundColor: wearBackground,
      visualDensity: VisualDensity.compact,
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: const StadiumBorder(),
        ),
      ),
    ),
  );
}
