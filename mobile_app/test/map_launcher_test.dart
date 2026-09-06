import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/map_launcher.dart';
import 'package:url_launcher/url_launcher.dart';

/// Registra los intentos y decide cuál "aplicación" está instalada.
class _FakeOpener {
  _FakeOpener({
    this.accepts = const <String>{},
    this.throwsOn = const <String>{},
  });

  final Set<String> accepts;
  final Set<String> throwsOn;
  final List<Uri> attempts = <Uri>[];

  Future<bool> call(
    Uri uri, {
    LaunchMode mode = LaunchMode.platformDefault,
  }) async {
    attempts.add(uri);
    if (throwsOn.contains(uri.scheme)) {
      throw StateError('esquema no registrado');
    }
    return accepts.contains(uri.scheme);
  }
}

void main() {
  const double latitude = 4.65;
  const double longitude = -74.05;

  test('Android usa el intent geo y deja la web como respaldo', () {
    const MapLauncher launcher = MapLauncher(isApplePlatform: false);
    final List<Uri> uris = launcher.candidateUris(
      latitude: latitude,
      longitude: longitude,
      label: 'Sabana de Bogotá',
    );

    expect(uris.first.scheme, 'geo');
    expect(uris.last.host, 'www.google.com');
    expect(uris.last.queryParameters['query'], '4.65,-74.05');
  });

  test('iOS ofrece Apple Maps primero cuando el sistema decide', () {
    const MapLauncher launcher = MapLauncher(isApplePlatform: true);
    final List<Uri> uris = launcher.candidateUris(
      latitude: latitude,
      longitude: longitude,
    );

    expect(uris.first.scheme, 'maps');
    expect(uris[1].scheme, 'comgooglemaps');
    expect(uris.last.host, 'www.google.com');
  });

  test('elegir Google Maps no ofrece Apple Maps ni siquiera en iOS', () {
    const MapLauncher launcher = MapLauncher(isApplePlatform: true);
    final List<Uri> uris = launcher.candidateUris(
      latitude: latitude,
      longitude: longitude,
      provider: MapProvider.google,
    );

    expect(uris.map((uri) => uri.scheme), isNot(contains('maps')));
    expect(uris.first.scheme, 'comgooglemaps');
  });

  test(
    'Una preferencia Apple antigua en Android abre el manejador de mapas',
    () {
      const MapLauncher launcher = MapLauncher(isApplePlatform: false);
      final List<Uri> uris = launcher.candidateUris(
        latitude: latitude,
        longitude: longitude,
        provider: MapProvider.apple,
      );

      expect(uris.first.scheme, 'geo');
      expect(uris.last.host, 'www.google.com');
    },
  );

  test('se usa la primera aplicación instalada', () async {
    final _FakeOpener opener = _FakeOpener(accepts: <String>{'comgooglemaps'});
    final MapLauncher launcher = MapLauncher(
      opener: opener.call,
      isApplePlatform: true,
    );

    expect(
      await launcher.openEpicenter(latitude: latitude, longitude: longitude),
      isTrue,
    );
    expect(opener.attempts.map((uri) => uri.scheme), <String>[
      'maps',
      'comgooglemaps',
    ]);
  });

  test('un esquema que lanza excepción no interrumpe el respaldo', () async {
    final _FakeOpener opener = _FakeOpener(
      accepts: <String>{'https'},
      throwsOn: <String>{'maps', 'comgooglemaps'},
    );
    final MapLauncher launcher = MapLauncher(
      opener: opener.call,
      isApplePlatform: true,
    );

    expect(
      await launcher.openEpicenter(latitude: latitude, longitude: longitude),
      isTrue,
    );
    expect(opener.attempts.map((uri) => uri.scheme), <String>[
      'maps',
      'comgooglemaps',
      'https',
    ]);
    expect(opener.attempts.last.host, 'maps.apple.com');
  });

  test('sin ninguna aplicación disponible se informa el fallo', () async {
    final _FakeOpener opener = _FakeOpener();
    final MapLauncher launcher = MapLauncher(
      opener: opener.call,
      isApplePlatform: false,
    );

    expect(
      await launcher.openEpicenter(latitude: latitude, longitude: longitude),
      isFalse,
    );
    expect(opener.attempts, isNotEmpty);
  });

  test('una etiqueta vacía no rompe la URL', () {
    const MapLauncher launcher = MapLauncher(isApplePlatform: true);
    final List<Uri> uris = launcher.candidateUris(
      latitude: latitude,
      longitude: longitude,
      label: '   ',
      provider: MapProvider.apple,
    );

    expect(uris.first.query, contains('Epicentro'));
  });

  test('la preferencia guardada se recupera por nombre', () {
    expect(MapProvider.fromName('apple'), MapProvider.apple);
    expect(MapProvider.fromName('google'), MapProvider.google);
    expect(MapProvider.fromName(null), MapProvider.system);
    expect(MapProvider.fromName('desconocido'), MapProvider.system);
  });
}
