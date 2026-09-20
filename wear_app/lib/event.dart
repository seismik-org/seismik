import 'package:seismik_shared/felt_area.dart';

/// Un sismo, con lo justo para una pantalla de reloj.
class WearEvent {
  const WearEvent({
    required this.id,
    required this.originTime,
    this.magnitude,
    this.depthKm,
    this.latitude,
    this.longitude,
    this.place,
    this.agency,
    this.preliminary = false,
  });

  factory WearEvent.fromMap(Map<String, dynamic> map) {
    double? number(String key) => switch (map[key]) {
      final num value => value.toDouble(),
      final String value => double.tryParse(value),
      _ => null,
    };
    final String type = '${map['type'] ?? ''}';
    return WearEvent(
      id: '${map['event_id'] ?? ''}',
      originTime:
          DateTime.tryParse(
            '${map['origin_time'] ?? map['detected_at'] ?? ''}',
          )?.toUtc() ??
          DateTime.now().toUtc(),
      magnitude: number('magnitude'),
      depthKm: number('depth_km'),
      latitude: number('latitude') ?? number('estimated_latitude'),
      longitude: number('longitude') ?? number('estimated_longitude'),
      place: map['place'] as String?,
      agency: map['agency'] as String?,
      preliminary: type == 'earthquake_candidate' || map['preliminary'] == true,
    );
  }

  final String id;
  final DateTime originTime;
  final double? magnitude;
  final double? depthKm;
  final double? latitude;
  final double? longitude;
  final String? place;
  final String? agency;
  final bool preliminary;

  String get magnitudeLabel =>
      magnitude == null ? '—' : magnitude!.toStringAsFixed(1);

  /// «hace 4 min», «hace 3 h»: en un reloj no cabe una fecha completa.
  String ago({DateTime? now}) {
    final Duration passed = (now ?? DateTime.now().toUtc()).difference(
      originTime,
    );
    if (passed.inMinutes < 1) return 'ahora';
    if (passed.inMinutes < 60) return 'hace ${passed.inMinutes} min';
    if (passed.inHours < 24) return 'hace ${passed.inHours} h';
    return 'hace ${passed.inDays} d';
  }

  /// Intensidad estimada donde está la persona, con el mismo modelo que usan
  /// la app de teléfono y el servidor para decidir la alarma.
  double? intensityAt(double? latitude, double? longitude) {
    final double? magnitude = this.magnitude;
    final double? eventLatitude = this.latitude;
    final double? eventLongitude = this.longitude;
    if (magnitude == null ||
        latitude == null ||
        longitude == null ||
        eventLatitude == null ||
        eventLongitude == null) {
      return null;
    }
    return estimatedIntensity(
      magnitude,
      depthKm,
      haversineKm(eventLatitude, eventLongitude, latitude, longitude),
    );
  }

  double? distanceKmFrom(double? latitude, double? longitude) {
    final double? eventLatitude = this.latitude;
    final double? eventLongitude = this.longitude;
    if (latitude == null ||
        longitude == null ||
        eventLatitude == null ||
        eventLongitude == null) {
      return null;
    }
    return haversineKm(eventLatitude, eventLongitude, latitude, longitude);
  }
}
