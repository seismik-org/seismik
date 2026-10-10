import 'dart:async';

import 'package:dynamic_color/dynamic_color.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Android 14+ publishes resolved dynamic roles, including OEM overlays and
/// contrast. Do not regenerate them from an accent or an older CorePalette.
/// Android 12–13 retain the dynamic_color compatibility implementation.
class SystemDynamicColorBuilder extends StatefulWidget {
  const SystemDynamicColorBuilder({required this.builder, super.key});
  final Widget Function(ColorScheme?, ColorScheme?) builder;

  static const channel = MethodChannel('com.seismik.app/dynamic-colors');

  static ColorScheme? scheme(Map<dynamic, dynamic>? roles, Brightness mode) {
    Color? color(String key) =>
        roles?[key] is int ? Color(roles![key] as int) : null;
    // Never accept an incomplete native response as a dynamic scheme.
    if (color('primary') == null ||
        color('on_primary') == null ||
        color('surface') == null ||
        color('on_surface') == null ||
        color('secondary') == null ||
        color('on_secondary') == null ||
        color('error') == null ||
        color('on_error') == null ||
        color('tertiary') == null) {
      return null;
    }
    return ColorScheme(
      brightness: mode,
      primary: color('primary')!,
      onPrimary: color('on_primary')!,
      primaryContainer: color('primary_container'),
      onPrimaryContainer: color('on_primary_container'),
      secondary: color('secondary')!,
      onSecondary: color('on_secondary')!,
      secondaryContainer: color('secondary_container'),
      onSecondaryContainer: color('on_secondary_container'),
      tertiary: color('tertiary'),
      onTertiary: color('on_tertiary'),
      tertiaryContainer: color('tertiary_container'),
      onTertiaryContainer: color('on_tertiary_container'),
      error: color('error')!,
      onError: color('on_error')!,
      errorContainer: color('error_container'),
      onErrorContainer: color('on_error_container'),
      surface: color('surface')!,
      onSurface: color('on_surface')!,
      onSurfaceVariant: color('on_surface_variant'),
      surfaceDim: color('surface_dim'),
      surfaceBright: color('surface_bright'),
      surfaceContainerLowest: color('surface_container_lowest'),
      surfaceContainerLow: color('surface_container_low'),
      surfaceContainer: color('surface_container'),
      surfaceContainerHigh: color('surface_container_high'),
      surfaceContainerHighest: color('surface_container_highest'),
      outline: color('outline'),
      outlineVariant: color('outline_variant'),
      inverseSurface: color('surface_inverse'),
      onInverseSurface: color('on_surface_inverse'),
      inversePrimary: color('primary_inverse'),
      surfaceTint: color('primary'),
      scrim: color('scrim'),
      shadow: const Color(0xFF000000),
      primaryFixed: color('primary_fixed'),
      primaryFixedDim: color('primary_fixed_dim'),
      onPrimaryFixed: color('on_primary_fixed'),
      onPrimaryFixedVariant: color('on_primary_fixed_variant'),
      secondaryFixed: color('secondary_fixed'),
      secondaryFixedDim: color('secondary_fixed_dim'),
      onSecondaryFixed: color('on_secondary_fixed'),
      onSecondaryFixedVariant: color('on_secondary_fixed_variant'),
      tertiaryFixed: color('tertiary_fixed'),
      tertiaryFixedDim: color('tertiary_fixed_dim'),
      onTertiaryFixed: color('on_tertiary_fixed'),
      onTertiaryFixedVariant: color('on_tertiary_fixed_variant'),
    );
  }

  @override
  State<SystemDynamicColorBuilder> createState() => _SystemDynamicColorState();
}

class _SystemDynamicColorState extends State<SystemDynamicColorBuilder>
    with WidgetsBindingObserver {
  ColorScheme? _light;
  ColorScheme? _dark;
  int _compatibilityRevision = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_refresh());
  }

  Future<void> _refresh() async {
    try {
      final roles = await SystemDynamicColorBuilder.channel
          .invokeMapMethod<String, dynamic>('getSchemes');
      final light = SystemDynamicColorBuilder.scheme(
        roles?['light'] as Map?,
        Brightness.light,
      );
      final dark = SystemDynamicColorBuilder.scheme(
        roles?['dark'] as Map?,
        Brightness.dark,
      );
      if (mounted) {
        setState(() {
          _light = light;
          _dark = dark;
          if (light == null && dark == null) _compatibilityRevision++;
        });
      }
    } on MissingPluginException {
      // Non-Android platforms and Android <14 use the compatibility builder.
    } on PlatformException {
      if (mounted) {
        setState(() {
          _light = null;
          _dark = null;
        });
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_refresh());
    }
  }

  @override
  void didChangePlatformBrightness() => unawaited(_refresh());

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => DynamicColorBuilder(
    key: ValueKey(_compatibilityRevision),
    builder: (light, dark) => widget.builder(_light ?? light, _dark ?? dark),
  );
}
