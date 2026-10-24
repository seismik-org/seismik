import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Maps without a cloud map ID also need a local style on older renderers.
/// Reading Theme here keeps maps in sync with system changes and app overrides.
abstract final class SeismikMapTheme {
  static MapColorScheme colorScheme(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark
      ? MapColorScheme.dark
      : MapColorScheme.light;

  static String? style(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? darkStyle : null;

  static const String darkStyle = '''[
    {"elementType":"geometry","stylers":[{"color":"#17212f"}]},
    {"elementType":"labels.text.fill","stylers":[{"color":"#cbd5e1"}]},
    {"elementType":"labels.text.stroke","stylers":[{"color":"#17212f"}]},
    {"featureType":"administrative","elementType":"geometry.stroke","stylers":[{"color":"#52647c"}]},
    {"featureType":"road","elementType":"geometry","stylers":[{"color":"#334155"}]},
    {"featureType":"road.highway","elementType":"geometry","stylers":[{"color":"#52647c"}]},
    {"featureType":"poi.park","elementType":"geometry","stylers":[{"color":"#1f3b37"}]},
    {"featureType":"water","elementType":"geometry","stylers":[{"color":"#0b172a"}]}
  ]''';
}
