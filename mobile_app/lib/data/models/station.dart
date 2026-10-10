class SeismicStation {
  const SeismicStation({
    required this.id,
    required this.network,
    required this.latitude,
    required this.longitude,
    this.countryCode,
    this.accessStatus,
    this.metadataCurrent,
  });

  factory SeismicStation.fromMap(Map<String, dynamic> map) => SeismicStation(
    id: map['station_id'].toString(),
    network: map['network'].toString(),
    latitude: (map['latitude'] as num).toDouble(),
    longitude: (map['longitude'] as num).toDouble(),
    countryCode: map['country_code']?.toString(),
    accessStatus: map['access_status']?.toString(),
    metadataCurrent: map['metadata_current'] as bool?,
  );

  final String id;
  final String network;
  final double latitude;
  final double longitude;
  final String? countryCode;
  final String? accessStatus;
  final bool? metadataCurrent;

  String get availabilityLabel {
    if (metadataCurrent == false) return 'Estación histórica · catálogo público';
    if (accessStatus == 'public_waveform_verified') {
      return 'Datos públicos verificados · no confirma emisión en vivo';
    }
    return 'Catálogo público · emisión en vivo no verificada';
  }
}
