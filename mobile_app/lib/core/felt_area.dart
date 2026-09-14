import 'dart:math' as math;

import '../data/models/seismic_event.dart';

/// Perímetro de sacudida: dónde se siente un sismo y con qué intensidad.
///
/// Réplica exacta de `src/api/felt_area.py`, que decide en el servidor a quién
/// le suena la alarma: el círculo del mapa y la alarma dibujan lo mismo. Las
/// pruebas de ambos lados comparten valores de referencia.
///
/// La intensidad de Mercalli modificada (MMI) describe lo que se siente en un
/// lugar. Se estima con modelos publicados según la profundidad:
/// - Corticales (hasta 40 km): Allen, Wald y Worden (2012).
/// - Intermedios (desde 70 km), como el Nido de Bucaramanga: Zhao et al.
///   (2006) para sismos intraplaca, convertido a MMI con Worden et al. (2012).
/// - Entre ambas profundidades se interpola para no crear un salto.

const double earthRadiusKm = 6371.0088;
const double defaultDepthKm = 10;
const double crustalUntilKm = 40;
const double intraslabFromKm = 70;
const double maxFeltRadiusKm = 2000;

/// III: se siente dentro de las casas.
const double feltIntensity = 3;

/// IV: lo siente casi todo el que está bajo techo.
const double lightIntensity = 4;

/// VI: lo siente todo el mundo; puede haber daños leves. Suena la alarma.
const double strongIntensity = 6;

/// VIII: daños considerables.
const double severeIntensity = 8;

const List<String> _roman = <String>[
  'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII',
];

double haversineKm(
  double latitudeA,
  double longitudeA,
  double latitudeB,
  double longitudeB,
) {
  double radians(double degrees) => degrees * math.pi / 180;
  final double phiA = radians(latitudeA);
  final double phiB = radians(latitudeB);
  final double deltaPhi = radians(latitudeB - latitudeA);
  final double deltaLambda = radians(longitudeB - longitudeA);
  final double inner =
      math.pow(math.sin(deltaPhi / 2), 2) +
      math.cos(phiA) * math.cos(phiB) * math.pow(math.sin(deltaLambda / 2), 2);
  return 2 * earthRadiusKm * math.asin(math.min(1, math.sqrt(inner)));
}

double _allen2012(double magnitude, double hypocentralKm) {
  final double distance = math.max(hypocentralKm, 1);
  final double nearSource = -0.209 + 2.042 * math.exp(magnitude - 5);
  double mmi =
      2.085 +
      1.428 * magnitude -
      1.402 * math.log(math.sqrt(distance * distance + nearSource * nearSource));
  if (distance > 50) mmi += 0.078 * math.log(distance / 50);
  return mmi;
}

double _zhao2006Intraslab(
  double magnitude,
  double depthKm,
  double hypocentralKm,
) {
  final double distance = math.max(hypocentralKm, 1);
  final double depth = math.min(depthKm, 125);
  final double lnPga =
      1.101 * magnitude -
      0.00564 * distance -
      math.log(distance + 0.0055 * math.exp(1.080 * magnitude)) +
      (depth >= 15 ? 0.01412 * (depth - 15) : 0) +
      1.344 + // Suelo firme (Vs30 de 300 a 600 m/s).
      0.1392 * (magnitude - 6.5) +
      0.1584 * math.pow(magnitude - 6.5, 2) -
      0.0529 +
      2.607 -
      0.528 * math.log(distance);
  final double logPga = lnPga / math.ln10; // cm/s²
  return logPga <= 1.57 ? 1.78 + 1.55 * logPga : -1.60 + 3.70 * logPga;
}

/// MMI esperada a [distanceKm] del epicentro, entre 1 y 12.
double estimatedIntensity(
  double magnitude,
  double? depthKm,
  double distanceKm,
) {
  final double depth = depthKm == null || depthKm < 0 ? defaultDepthKm : depthKm;
  final double hypocentral = math.sqrt(distanceKm * distanceKm + depth * depth);
  final double weight =
      ((depth - crustalUntilKm) / (intraslabFromKm - crustalUntilKm))
          .clamp(0.0, 1.0);
  double mmi = 0;
  if (weight < 1) mmi += (1 - weight) * _allen2012(magnitude, hypocentral);
  if (weight > 0) {
    mmi += weight * _zhao2006Intraslab(magnitude, depth, hypocentral);
  }
  return mmi.clamp(1.0, 12.0);
}

/// Distancia epicentral hasta donde se espera al menos [intensity], o `null`
/// si ni siquiera sobre el epicentro se alcanza.
double? feltRadiusKm(double magnitude, double? depthKm, double intensity) {
  if (estimatedIntensity(magnitude, depthKm, 0) < intensity) return null;
  if (estimatedIntensity(magnitude, depthKm, maxFeltRadiusKm) >= intensity) {
    return maxFeltRadiusKm;
  }
  double low = 0;
  double high = maxFeltRadiusKm;
  for (int iteration = 0; iteration < 40; iteration++) {
    final double middle = (low + high) / 2;
    if (estimatedIntensity(magnitude, depthKm, middle) >= intensity) {
      low = middle;
    } else {
      high = middle;
    }
  }
  return low;
}

int _level(double intensity) => (intensity + 0.5).floor().clamp(1, 12);

String intensityRoman(double intensity) => _roman[_level(intensity) - 1];

/// Nombre de la sacudida percibida, como en los mapas del USGS.
String intensityName(double intensity) => switch (_level(intensity)) {
  1 => 'no sentido',
  2 || 3 => 'débil',
  4 => 'ligera',
  5 => 'moderada',
  6 => 'fuerte',
  7 => 'muy fuerte',
  8 => 'severa',
  9 => 'violenta',
  _ => 'extrema',
};

/// Un anillo del perímetro: hasta dónde llega una intensidad.
class PerimeterRing {
  const PerimeterRing({
    required this.intensity,
    required this.radiusKm,
    required this.label,
  });

  final double intensity;
  final double radiusKm;
  final String label;
}

/// Anillos que se dibujan, del más externo al más interno.
const List<({double intensity, String label})> perimeterLevels =
    <({double intensity, String label})>[
      (intensity: feltIntensity, label: 'Se sintió'),
      (intensity: lightIntensity, label: 'Sacudida ligera'),
      (intensity: strongIntensity, label: 'Sacudida fuerte'),
      (intensity: severeIntensity, label: 'Sacudida severa'),
    ];

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
