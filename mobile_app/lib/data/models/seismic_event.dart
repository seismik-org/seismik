class SeismicEvent {
  const SeismicEvent({
    required this.id,
    required this.type,
    required this.detectedAt,
    this.latitude,
    this.longitude,
    this.magnitude,
    this.depthKm,
    this.agency,
    this.place,
    this.officialUrl,
    this.officialEventId,
    this.countryCode,
  });

  factory SeismicEvent.fromMap(Map<String, dynamic> map) {
    double? number(String key) => switch (map[key]) {
      final num value => value.toDouble(),
      final String value => double.tryParse(value),
      _ => null,
    };

    return SeismicEvent(
      id: (map['event_id'] ?? map['id'] ?? 'unknown').toString(),
      type: (map['type'] ?? 'earthquake_candidate').toString(),
      detectedAt:
          DateTime.tryParse(
            (map['detected_at'] ?? map['origin_time'] ?? '').toString(),
          )?.toUtc() ??
          DateTime.now().toUtc(),
      latitude: number('latitude') ?? number('estimated_latitude'),
      longitude: number('longitude') ?? number('estimated_longitude'),
      magnitude: number('magnitude'),
      depthKm: number('depth_km'),
      agency: map['agency']?.toString(),
      place: map['place']?.toString(),
      officialUrl: map['official_url']?.toString(),
      officialEventId: map['official_event_id']?.toString(),
      countryCode: map['country_code']?.toString(),
    );
  }

  final String id;
  final String type;
  final DateTime detectedAt;
  final double? latitude;
  final double? longitude;
  final double? magnitude;
  final double? depthKm;
  final String? agency;
  final String? place;
  final String? officialUrl;
  final String? officialEventId;
  final String? countryCode;

  bool get isOfficial => type == 'official_report_update';
}
