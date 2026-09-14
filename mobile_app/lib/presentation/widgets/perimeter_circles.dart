import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../core/felt_area.dart';
import '../../data/models/seismic_event.dart';

/// Sismos recientes cuyo perímetro se dibuja en el mapa principal.
const Duration recentPerimeterAge = Duration(hours: 72);
const int maxRecentPerimeters = 30;

/// Del amarillo (se sintió) al rojo oscuro (daños probables).
Color perimeterColor(double intensity) {
  if (intensity >= severeIntensity) return const Color(0xFF8E0012);
  if (intensity >= strongIntensity) return const Color(0xFFE53935);
  if (intensity >= lightIntensity) return const Color(0xFFFB8C00);
  return const Color(0xFFFFB300);
}

/// Anillos del perímetro de un sismo, listos para `GoogleMap.circles`.
///
/// [levels] limita qué intensidades se dibujan; por defecto, todas.
Set<Circle> perimeterCircles(SeismicEvent event, {List<double>? levels}) {
  final double? latitude = event.latitude;
  final double? longitude = event.longitude;
  if (latitude == null || longitude == null) return <Circle>{};
  return <Circle>{
    for (final PerimeterRing ring in feltPerimeter(event))
      if (levels == null || levels.contains(ring.intensity))
        Circle(
          circleId: CircleId(
            'perimeter.${event.id}.${ring.intensity.toStringAsFixed(0)}',
          ),
          center: LatLng(latitude, longitude),
          radius: ring.radiusKm * 1000,
          strokeWidth: ring.intensity == feltIntensity ? 2 : 1,
          strokeColor: perimeterColor(ring.intensity).withValues(alpha: 0.85),
          fillColor: perimeterColor(
            ring.intensity,
          ).withValues(alpha: ring.intensity == feltIntensity ? 0.08 : 0.14),
          zIndex: ring.intensity.round(),
        ),
  };
}

/// En el mapa principal sólo se ve dónde se sintió cada sismo reciente y su
/// zona de sacudida fuerte; el detalle del sismo muestra todos los anillos.
Set<Circle> recentPerimeterCircles(List<SeismicEvent> events, {DateTime? now}) {
  final DateTime cutoff = (now ?? DateTime.now().toUtc()).subtract(
    recentPerimeterAge,
  );
  final Set<Circle> circles = <Circle>{};
  int drawn = 0;
  for (final SeismicEvent event in events) {
    if (drawn >= maxRecentPerimeters) break;
    if (event.detectedAt.isBefore(cutoff)) continue;
    final Set<Circle> rings = perimeterCircles(
      event,
      levels: const <double>[feltIntensity, strongIntensity],
    );
    if (rings.isEmpty) continue;
    circles.addAll(rings);
    drawn++;
  }
  return circles;
}

/// Zoom con el que el perímetro de [radiusKm] cabe en [widthPx] de mapa.
double perimeterZoom({
  required double radiusKm,
  required double latitude,
  required double widthPx,
}) {
  const double metersPerPixelAtZoomZero = 156543.03392;
  final double diameterMeters = math.max(radiusKm, 2) * 2 * 1000 * 1.25;
  final double scale =
      metersPerPixelAtZoomZero *
      math.cos(latitude * math.pi / 180) *
      widthPx /
      diameterMeters;
  return (math.log(scale) / math.ln2).clamp(2.0, 12.0);
}

/// Conserva los círculos mientras la lista de sismos no cambie.
class PerimeterCircleCache {
  List<SeismicEvent>? _events;
  Set<Circle>? _circles;

  Set<Circle> resolve(
    List<SeismicEvent> events,
    Set<Circle> Function() build,
  ) {
    final Set<Circle>? cached = _circles;
    if (cached != null && identical(events, _events)) return cached;
    _events = events;
    return _circles = build();
  }
}
