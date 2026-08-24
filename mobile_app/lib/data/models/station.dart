class SeismicStation {
  const SeismicStation({
    required this.id,
    required this.network,
    required this.latitude,
    required this.longitude,
    this.countryCode,
  });

  factory SeismicStation.fromMap(Map<String, dynamic> map) => SeismicStation(
    id: map['station_id'].toString(),
    network: map['network'].toString(),
    latitude: (map['latitude'] as num).toDouble(),
    longitude: (map['longitude'] as num).toDouble(),
    countryCode: map['country_code']?.toString(),
  );

  final String id;
  final String network;
  final double latitude;
  final double longitude;
  final String? countryCode;
}
