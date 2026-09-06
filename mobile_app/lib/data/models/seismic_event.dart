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
    this.sourceId,
    this.magnitudeType,
    this.reviewStatus,
    this.updatedAt,
    this.attribution,
    this.tsunami,
    this.preliminary = false,
    this.algorithm,
    this.zoneId,
    this.countryCodes = const <String>[],
    this.coincidenceWindowSeconds,
    this.requiredStations,
    this.stationCount,
    this.waveStrengthIndex,
    this.magnitudeEstimateStatus,
    this.stations = const <SeismicStationTrigger>[],
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
      sourceId: map['source_id']?.toString(),
      magnitudeType: map['magnitude_type']?.toString(),
      reviewStatus: map['review_status']?.toString(),
      updatedAt: DateTime.tryParse(
        (map['updated_at'] ?? '').toString(),
      )?.toUtc(),
      attribution: map['attribution']?.toString(),
      tsunami: map['tsunami'] as bool?,
      preliminary:
          map['preliminary'] == true ||
          map['type']?.toString() == 'earthquake_candidate',
      algorithm: map['algorithm']?.toString(),
      zoneId: map['zone_id']?.toString(),
      countryCodes: (map['country_codes'] as List<dynamic>? ?? <dynamic>[])
          .map((value) => value.toString())
          .toList(growable: false),
      coincidenceWindowSeconds: number('coincidence_window_seconds'),
      requiredStations: (map['required_stations'] as num?)?.toInt(),
      stationCount: (map['station_count'] as num?)?.toInt(),
      waveStrengthIndex: number('wave_strength_index'),
      magnitudeEstimateStatus: map['magnitude_estimate_status']?.toString(),
      stations: (map['stations'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(SeismicStationTrigger.fromMap)
          .toList(growable: false),
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
  final String? sourceId;
  final String? magnitudeType;
  final String? reviewStatus;
  final DateTime? updatedAt;
  final String? attribution;
  final bool? tsunami;
  final bool preliminary;
  final String? algorithm;
  final String? zoneId;
  final List<String> countryCodes;
  final double? coincidenceWindowSeconds;
  final int? requiredStations;
  final int? stationCount;
  final double? waveStrengthIndex;
  final String? magnitudeEstimateStatus;
  final List<SeismicStationTrigger> stations;

  bool get isOfficial => type == 'official_report_update';
  bool get isPreliminary => preliminary;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'event_id': id,
    'type': type,
    'origin_time': detectedAt.toIso8601String(),
    'latitude': latitude,
    'longitude': longitude,
    'magnitude': magnitude,
    'depth_km': depthKm,
    'agency': agency,
    'place': place,
    'official_url': officialUrl,
    'official_event_id': officialEventId,
    'country_code': countryCode,
    'source_id': sourceId,
    'magnitude_type': magnitudeType,
    'review_status': reviewStatus,
    'updated_at': updatedAt?.toIso8601String(),
    'attribution': attribution,
    'tsunami': tsunami,
    'preliminary': preliminary,
    'algorithm': algorithm,
    'zone_id': zoneId,
    'country_codes': countryCodes,
    'coincidence_window_seconds': coincidenceWindowSeconds,
    'required_stations': requiredStations,
    'station_count': stationCount,
    'wave_strength_index': waveStrengthIndex,
    'magnitude_estimate_status': magnitudeEstimateStatus,
    'stations': stations
        .map((station) => station.toMap())
        .toList(growable: false),
  };
}

class SeismicStationTrigger {
  const SeismicStationTrigger({
    required this.providerId,
    required this.stationId,
    required this.triggerTime,
    required this.staLtaRatio,
    this.countryCode,
    this.streamId,
    this.packetLagSeconds,
    this.peakAmplitudeCounts,
    this.noiseRmsCounts,
  });

  factory SeismicStationTrigger.fromMap(Map<String, dynamic> map) {
    double? number(String key) => switch (map[key]) {
      final num value => value.toDouble(),
      final String value => double.tryParse(value),
      _ => null,
    };
    return SeismicStationTrigger(
      providerId: (map['provider_id'] ?? 'seedlink').toString(),
      stationId: (map['station_id'] ?? '—').toString(),
      triggerTime:
          DateTime.tryParse((map['trigger_time'] ?? '').toString())?.toUtc() ??
          DateTime.now().toUtc(),
      staLtaRatio: number('sta_lta_ratio') ?? 0,
      countryCode: map['country_code']?.toString(),
      streamId: map['stream_id']?.toString(),
      packetLagSeconds: number('packet_lag_seconds'),
      peakAmplitudeCounts: number('peak_amplitude_counts'),
      noiseRmsCounts: number('noise_rms_counts'),
    );
  }

  final String providerId;
  final String stationId;
  final DateTime triggerTime;
  final double staLtaRatio;
  final String? countryCode;
  final String? streamId;
  final double? packetLagSeconds;
  final double? peakAmplitudeCounts;
  final double? noiseRmsCounts;

  Map<String, dynamic> toMap() => <String, dynamic>{
    'provider_id': providerId,
    'station_id': stationId,
    'trigger_time': triggerTime.toIso8601String(),
    'sta_lta_ratio': staLtaRatio,
    'country_code': countryCode,
    'stream_id': streamId,
    'packet_lag_seconds': packetLagSeconds,
    'peak_amplitude_counts': peakAmplitudeCounts,
    'noise_rms_counts': noiseRmsCounts,
  };
}
