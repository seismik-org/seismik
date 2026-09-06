import 'dart:io';

import 'package:url_launcher/url_launcher.dart';

/// Proveedor cartográfico elegido por la persona para abrir un epicentro.
enum MapProvider {
  /// Deja que el sistema decida: Apple Maps en iOS, Google Maps en Android.
  system,
  google,
  apple;

  static MapProvider fromName(String? value) => switch (value) {
    'google' => MapProvider.google,
    'apple' => MapProvider.apple,
    _ => MapProvider.system,
  };

  String get label => switch (this) {
    MapProvider.system => 'Según el sistema',
    MapProvider.google => 'Google Maps',
    MapProvider.apple => 'Apple Maps',
  };
}

/// Firma inyectable para poder probar el orden de intentos sin plugins nativos.
typedef UrlOpener = Future<bool> Function(Uri uri, {LaunchMode mode});

Future<bool> _defaultOpener(
  Uri uri, {
  LaunchMode mode = LaunchMode.platformDefault,
}) => launchUrl(uri, mode: mode);

/// Abre el epicentro de un sismo en la aplicación de mapas disponible.
///
/// Se intentan los esquemas nativos en orden de preferencia y, si ninguno está
/// instalado, siempre queda la web de Google Maps, que funciona en cualquier
/// navegador. Apple Maps sólo se ofrece en iOS/macOS porque su esquema `maps:`
/// no existe en Android.
class MapLauncher {
  const MapLauncher({UrlOpener opener = _defaultOpener, bool? isApplePlatform})
    : _opener = opener,
      _isApplePlatform = isApplePlatform;

  final UrlOpener _opener;
  final bool? _isApplePlatform;

  bool get _apple => _isApplePlatform ?? (Platform.isIOS || Platform.isMacOS);

  /// URIs candidatas, de la más específica a la de respaldo web.
  List<Uri> candidateUris({
    required double latitude,
    required double longitude,
    String? label,
    MapProvider provider = MapProvider.system,
  }) {
    final String point = '$latitude,$longitude';
    final String name = Uri.encodeComponent(
      (label == null || label.trim().isEmpty) ? 'Epicentro' : label.trim(),
    );
    final Uri googleApp = Uri.parse(
      'comgooglemaps://?q=$point&center=$point&zoom=9',
    );
    final Uri googleGeo = Uri.parse('geo:$point?q=$point($name)');
    final Uri appleApp = Uri.parse('maps://?ll=$point&q=$name');
    final Uri appleWeb = Uri.parse('https://maps.apple.com/?ll=$point&q=$name');
    final Uri googleWeb = Uri.parse(
      'https://www.google.com/maps/search/?api=1&query=$point',
    );

    final List<Uri> ordered = <Uri>[];
    switch (provider) {
      case MapProvider.google:
        ordered.addAll(<Uri>[if (_apple) googleApp else googleGeo, googleWeb]);
      case MapProvider.apple:
        if (_apple) {
          ordered.addAll(<Uri>[appleApp, appleWeb]);
        } else {
          // Apple Maps no existe como aplicación Android. Si una preferencia
          // antigua quedó guardada, no se debe dejar un botón que parezca roto:
          // se abre el manejador de mapas instalado en Android.
          ordered.add(googleGeo);
        }
        ordered.add(googleWeb);
      case MapProvider.system:
        if (_apple) {
          ordered.addAll(<Uri>[appleApp, googleApp, appleWeb]);
        } else {
          ordered.add(googleGeo);
        }
        ordered.add(googleWeb);
    }
    // Conserva el orden y descarta repeticiones entre ramas.
    final List<Uri> unique = <Uri>[];
    for (final Uri uri in ordered) {
      if (!unique.contains(uri)) unique.add(uri);
    }
    return unique;
  }

  /// Devuelve `true` si alguna aplicación aceptó abrir el epicentro.
  Future<bool> openEpicenter({
    required double latitude,
    required double longitude,
    String? label,
    MapProvider provider = MapProvider.system,
  }) async {
    final List<Uri> uris = candidateUris(
      latitude: latitude,
      longitude: longitude,
      label: label,
      provider: provider,
    );
    for (final Uri uri in uris) {
      try {
        // Los intents nativos abren Maps; el último respaldo HTTPS se abre en
        // Chrome Custom Tabs / Safari integrado, no en el navegador externo.
        final LaunchMode mode = (uri.scheme == 'https' || uri.scheme == 'http')
            ? LaunchMode.inAppBrowserView
            : LaunchMode.externalApplication;
        if (await _opener(uri, mode: mode)) return true;
      } catch (_) {
        // Un esquema no registrado lanza excepción en algunos dispositivos;
        // se continúa con la siguiente alternativa.
      }
    }
    return false;
  }
}
