import 'package:geolocator/geolocator.dart';

import '../data/models/seismic_event.dart';

/// Distance ranks suggestions; it does not prove that a quake was felt.
double? reportEventDistance(SeismicEvent event, double? lat, double? lon) {
  if (lat == null ||
      lon == null ||
      event.latitude == null ||
      event.longitude == null) {
    return null;
  }
  return Geolocator.distanceBetween(
        lat,
        lon,
        event.latitude!,
        event.longitude!,
      ) /
      1000;
}

List<SeismicEvent> reportEventChoices(
  Iterable<SeismicEvent> events, {
  required DateTime now,
  double? latitude,
  double? longitude,
}) {
  final byId = <String, SeismicEvent>{};
  for (final event in events) {
    final age = now.toUtc().difference(event.detectedAt.toUtc());
    if (event.id.isEmpty ||
        event.id == 'unknown' ||
        event.id.startsWith('drill-') ||
        event.sourceId == 'simulation' ||
        age.isNegative ||
        age > const Duration(days: 7)) {
      continue;
    }
    byId[event.id] = event;
  }
  final choices = byId.values.toList();
  choices.sort((a, b) {
    final da = reportEventDistance(a, latitude, longitude);
    final db = reportEventDistance(b, latitude, longitude);
    if (da != null && db != null && da != db) return da.compareTo(db);
    if (da != null && db == null) return -1;
    if (da == null && db != null) return 1;
    return b.detectedAt.compareTo(a.detectedAt);
  });
  return choices;
}
