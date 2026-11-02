import 'package:seismik_shared/felt_area.dart';

/// Lo que una organización informó de un mismo sismo, sin tocarlo: cada una
/// conserva su valor, su escala y su estado de revisión. No se promedian.
class WearSourceReport {
  const WearSourceReport({
    required this.agency,
    this.magnitude,
    this.magnitudeText,
    this.magnitudeType,
    this.reviewStatus,
  });

  factory WearSourceReport.fromMap(Map<String, dynamic> map) {
    final Object? raw = map['magnitude'];
    final double? magnitude = switch (raw) {
      final num value => value.toDouble(),
      final String value => double.tryParse(value.trim()),
      _ => null,
    };
    String? text(String key) {
      final String value = '${map[key] ?? ''}'.trim();
      return value.isEmpty ? null : value;
    }

    return WearSourceReport(
      agency: text('agency') ?? text('source_id') ?? 'Fuente',
      magnitude: magnitude,
      // Se conserva la precisión con que la organización publicó el valor:
      // 3.13 no debe leerse como 3.1 al compararlo con otra escala.
      magnitudeText: magnitude == null
          ? null
          : raw is String
          ? raw.trim()
          : raw is int
          ? '$raw.0'
          : '$magnitude',
      magnitudeType: text('magnitude_type'),
      reviewStatus: text('review_status'),
    );
  }

  final String agency;
  final double? magnitude;
  final String? magnitudeText;
  final String? magnitudeType;
  final String? reviewStatus;

  String get valueLabel => magnitudeText ?? 'Sin magnitud';
}

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
    this.sourceReports = const <WearSourceReport>[],
    this.relatedEventIds = const <String>[],
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
      sourceReports: <WearSourceReport>[
        for (final Object? report
            in (map['source_reports'] is List
                ? map['source_reports'] as List<Object?>
                : const <Object?>[]))
          if (report is Map<String, dynamic>) WearSourceReport.fromMap(report),
      ],
      relatedEventIds: <String>[
        for (final Object? id
            in (map['related_event_ids'] is List
                ? map['related_event_ids'] as List<Object?>
                : const <Object?>[]))
          if (id != null && '$id'.isNotEmpty) '$id',
      ],
    );
  }

  /// Lista del servidor o de la caché, con un solo elemento por sismo.
  ///
  /// La API ya agrupa los reportes de cada organización, pero una caché guardada
  /// por una versión anterior, o un reintento, puede traer el mismo sismo bajo
  /// otro identificador: se reconoce por los identificadores asociados.
  static List<WearEvent> parseList(Object? raw) {
    final List<WearEvent> parsed = <WearEvent>[
      if (raw is List)
        for (final Object? item in raw)
          if (item is Map<String, dynamic>) WearEvent.fromMap(item),
    ];
    final Set<String> known = <String>{};
    final List<WearEvent> unique = <WearEvent>[];
    for (final WearEvent event in parsed) {
      final Set<String> ids = <String>{
        if (event.id.isNotEmpty) event.id,
        ...event.relatedEventIds,
      };
      if (ids.isNotEmpty && ids.any(known.contains)) continue;
      known.addAll(ids);
      unique.add(event);
    }
    return List<WearEvent>.unmodifiable(unique);
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
  final List<WearSourceReport> sourceReports;
  final List<String> relatedEventIds;

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

/// El sismo que encabeza la pantalla del reloj.
///
/// En una muñeca lo que importa es el que te tocó: el más reciente que alcanzó
/// al menos «se sintió» (III) donde estás. Si ninguno llegó hasta ahí —o no se
/// conoce la ubicación— encabeza el último del catálogo, y la pantalla dice
/// que fue lejos.
WearEvent? headlineEvent(
  List<WearEvent> events, {
  double? latitude,
  double? longitude,
}) {
  if (events.isEmpty) return null;
  if (latitude == null || longitude == null) return events.first;
  for (final WearEvent event in events) {
    final double? intensity = event.intensityAt(latitude, longitude);
    if (intensity != null && intensity >= feltIntensity) return event;
  }
  return events.first;
}
