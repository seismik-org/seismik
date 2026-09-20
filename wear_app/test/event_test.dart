import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/event.dart';

/// El reloj usa el mismo modelo de sacudida que el teléfono y el servidor.
/// Estas pruebas fijan lo que se muestra en la muñeca: la magnitud, la
/// antigüedad y la intensidad estimada donde está la persona.
void main() {
  final DateTime now = DateTime.utc(2026, 9, 19, 20, 0);

  Map<String, dynamic> payload({
    String time = '2026-09-19T19:56:00Z',
    Object? magnitude = 5.2,
    Object? depth = 12.0,
    double latitude = 6.80,
    double longitude = -73.10,
  }) => <String, dynamic>{
    'event_id': 'sgc_colombia:SGC2026abc',
    'type': 'official_report_update',
    'origin_time': time,
    'magnitude': magnitude,
    'depth_km': depth,
    'latitude': latitude,
    'longitude': longitude,
    'place': 'Los Santos, Santander',
    'agency': 'Servicio Geológico Colombiano',
  };

  test('un sismo del servidor llega completo a la pantalla', () {
    final WearEvent event = WearEvent.fromMap(payload());

    expect(event.magnitudeLabel, '5.2');
    expect(event.place, 'Los Santos, Santander');
    expect(event.preliminary, isFalse);
    expect(event.ago(now: now), 'hace 4 min');
  });

  test('la API puede mandar los números como texto', () {
    final WearEvent event = WearEvent.fromMap(
      payload(magnitude: '4.1', depth: '150'),
    );

    expect(event.magnitude, 4.1);
    expect(event.depthKm, 150);
  });

  test('una detección preliminar sin magnitud no inventa un número', () {
    final WearEvent event = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'cand-1',
      'type': 'earthquake_candidate',
      'detected_at': '2026-09-19T19:59:30Z',
    });

    expect(event.preliminary, isTrue);
    expect(event.magnitude, isNull);
    expect(event.magnitudeLabel, '—');
    expect(event.ago(now: now), 'ahora');
  });

  test('la intensidad es la del lugar donde está la persona', () {
    final WearEvent event = WearEvent.fromMap(payload());

    // En el epicentro sacude mucho más que a 300 km.
    final double? aqui = event.intensityAt(6.80, -73.10);
    final double? lejos = event.intensityAt(4.65, -74.05);

    expect(aqui, isNotNull);
    expect(lejos, isNotNull);
    expect(aqui!, greaterThan(lejos!));
    expect(event.distanceKmFrom(4.65, -74.05)!, closeTo(261, 5));
  });

  test('sin ubicación no se estima nada', () {
    final WearEvent event = WearEvent.fromMap(payload());

    expect(event.intensityAt(null, null), isNull);
    expect(event.distanceKmFrom(null, null), isNull);
  });

  test('un sismo sin epicentro tampoco estima', () {
    final WearEvent event = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'sin-ubicar',
      'origin_time': '2026-09-19T19:00:00Z',
      'magnitude': 4.0,
    });

    expect(event.intensityAt(4.65, -74.05), isNull);
    expect(event.ago(now: now), 'hace 1 h');
  });

  group('qué sismo encabeza la pantalla', () {
    // Bucaramanga: cerca del nido sísmico. Texas: al otro lado del continente.
    final WearEvent lejano = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'usgs:texas',
      'origin_time': '2026-09-19T19:58:00Z',
      'magnitude': 2.6,
      'depth_km': 8.0,
      'latitude': 32.7,
      'longitude': -101.9,
      'place': '8 km SSE of Barstow, Texas',
    });
    final WearEvent cercano = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'sgc:santander',
      'origin_time': '2026-09-19T19:30:00Z',
      'magnitude': 4.6,
      'depth_km': 12.0,
      'latitude': 6.80,
      'longitude': -73.10,
      'place': 'Los Santos, Santander',
    });

    test('gana el que se sintió aquí, aunque sea más viejo', () {
      final WearEvent? elegido = headlineEvent(
        <WearEvent>[lejano, cercano],
        latitude: 7.10,
        longitude: -73.12,
      );

      expect(elegido?.place, 'Los Santos, Santander');
    });

    test('sin ubicación se muestra el más reciente', () {
      final WearEvent? elegido = headlineEvent(<WearEvent>[lejano, cercano]);

      expect(elegido?.place, '8 km SSE of Barstow, Texas');
    });

    test('si ninguno se sintió aquí, encabeza el más reciente', () {
      final WearEvent? elegido = headlineEvent(
        <WearEvent>[lejano, cercano],
        latitude: 4.65,
        longitude: -74.05,
      );

      expect(elegido?.place, '8 km SSE of Barstow, Texas');
    });

    test('sin sismos no hay nada que encabezar', () {
      expect(headlineEvent(<WearEvent>[]), isNull);
    });
  });
}
