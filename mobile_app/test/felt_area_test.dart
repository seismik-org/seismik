import 'package:flutter_test/flutter_test.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:seismik/core/felt_area.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/presentation/widgets/perimeter_circles.dart';

SeismicEvent quake(
  String id, {
  double? magnitude = 6.0,
  double? depthKm = 10,
  DateTime? origin,
}) => SeismicEvent.fromMap(<String, dynamic>{
  'event_id': id,
  'type': 'official_report_update',
  'origin_time': (origin ?? DateTime.utc(2026, 9, 13, 18)).toIso8601String(),
  'latitude': 4.65,
  'longitude': -74.05,
  'magnitude': magnitude,
  'depth_km': depthKm,
});

void main() {
  // tests/test_felt_area.py comprueba los mismos valores: la alarma del
  // servidor y el círculo del mapa deben coincidir.
  const List<(double, double?, double, double)> intensities =
      <(double, double?, double, double)>[
        (4.0, 150, 40, 3.066),
        (4.0, 150, 290, 1.652),
        (4.0, 10, 0, 4.567),
        (6.0, 10, 100, 4.242),
        (7.0, 10, 281, 4.308),
        (6.0, 55, 0, 5.367),
        (4.5, null, 0, 5.275),
      ];
  const List<(double, double, double, double)> radii =
      <(double, double, double, double)>[
        (4.0, 10, feltIntensity, 28.93),
        (4.0, 150, feltIntensity, 60.28),
        (6.0, 10, strongIntensity, 25.19),
        (7.0, 10, strongIntensity, 76.28),
      ];

  test('la intensidad coincide con la referencia del servidor', () {
    for (final (double m, double? depth, double distance, double expected)
        in intensities) {
      expect(
        estimatedIntensity(m, depth, distance),
        closeTo(expected, 0.001),
        reason: 'M$m a $distance km, profundidad $depth',
      );
    }
  });

  test('el radio de cada anillo coincide con la referencia del servidor', () {
    for (final (double m, double depth, double intensity, double expected)
        in radii) {
      expect(feltRadiusKm(m, depth, intensity), closeTo(expected, 0.01));
    }
    expect(feltRadiusKm(2.5, 10, feltIntensity), isNull);
    expect(feltRadiusKm(8.5, 30, feltIntensity), maxFeltRadiusKm);
  });

  test('un sismo del Nido de Bucaramanga se siente cerca y no en Bogotá', () {
    expect(
      intensityAtPlace(quakeAt(6.80, -73.10, 4.0, 150), 7.119, -73.123),
      greaterThanOrEqualTo(feltIntensity),
    );
    expect(
      intensityAtPlace(quakeAt(6.80, -73.10, 4.0, 150), 4.711, -74.072),
      lessThan(feltIntensity),
    );
  });

  test('el perímetro lista sólo los anillos que se alcanzan', () {
    expect(
      feltPerimeter(quake('m6')).map((ring) => ring.intensity),
      <double>[feltIntensity, lightIntensity, strongIntensity],
    );
    expect(feltPerimeter(quake('sin-magnitud', magnitude: null)), isEmpty);
    expect(feltPerimeter(quake('imperceptible', magnitude: 2.5)), isEmpty);
    expect(intensityRoman(3.066), 'III');
    expect(intensityName(6.2), 'fuerte');
  });

  test('el mapa principal dibuja sólo sismos recientes y con perímetro', () {
    final DateTime now = DateTime.utc(2026, 9, 13, 20);
    final Set<Circle> circles = recentPerimeterCircles(<SeismicEvent>[
      quake('reciente', origin: now.subtract(const Duration(hours: 2))),
      quake('viejo', origin: now.subtract(const Duration(days: 5))),
      quake('pequeno', magnitude: 2.5, origin: now),
    ], now: now);

    expect(
      circles.map((circle) => circle.circleId.value).toSet(),
      <String>{'perimeter.reciente.3', 'perimeter.reciente.6'},
    );
    final Circle felt = circles.firstWhere(
      (circle) => circle.circleId.value.endsWith('.3'),
    );
    expect(felt.radius, closeTo(256.92 * 1000, 10));
  });

  test('el zoom encuadra perímetros pequeños y grandes', () {
    final double small = perimeterZoom(
      radiusKm: 20,
      latitude: 4.65,
      widthPx: 360,
    );
    final double large = perimeterZoom(
      radiusKm: 700,
      latitude: 4.65,
      widthPx: 360,
    );
    expect(small, greaterThan(large));
    expect(large, inInclusiveRange(2.0, 12.0));
  });
}

SeismicEvent quakeAt(
  double latitude,
  double longitude,
  double magnitude,
  double depthKm,
) => SeismicEvent.fromMap(<String, dynamic>{
  'event_id': 'nido',
  'type': 'official_report_update',
  'origin_time': '2026-09-13T17:55:25Z',
  'latitude': latitude,
  'longitude': longitude,
  'magnitude': magnitude,
  'depth_km': depthKm,
});
