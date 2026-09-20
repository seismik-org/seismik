/// La matemática de la sacudida vive en `packages/seismik_shared`, para que
/// la app de reloj use el mismo modelo sin una cuarta copia de las fórmulas.
/// Aquí quedan sólo los ayudantes que conocen `SeismicEvent`.
library;

import 'package:seismik_shared/felt_area.dart';

import '../data/models/seismic_event.dart';

export 'package:seismik_shared/felt_area.dart';

/// El perímetro de un sismo; vacío si no tiene magnitud o epicentro, o si no
/// se espera que se sienta en superficie.
List<PerimeterRing> feltPerimeter(SeismicEvent event) {
  final double? magnitude = event.magnitude;
  if (magnitude == null || event.latitude == null || event.longitude == null) {
    return const <PerimeterRing>[];
  }
  return <PerimeterRing>[
    for (final ({double intensity, String label}) level in perimeterLevels)
      if (feltRadiusKm(magnitude, event.depthKm, level.intensity)
          case final double radius)
        PerimeterRing(
          intensity: level.intensity,
          radiusKm: radius,
          label: level.label,
        ),
  ];
}

/// Intensidad esperada en un lugar, o `null` si el sismo no tiene magnitud o
/// epicentro.
double? intensityAtPlace(SeismicEvent event, double latitude, double longitude) {
  final double? magnitude = event.magnitude;
  final double? epicenterLatitude = event.latitude;
  final double? epicenterLongitude = event.longitude;
  if (magnitude == null ||
      epicenterLatitude == null ||
      epicenterLongitude == null) {
    return null;
  }
  return estimatedIntensity(
    magnitude,
    event.depthKm,
    haversineKm(epicenterLatitude, epicenterLongitude, latitude, longitude),
  );
}
