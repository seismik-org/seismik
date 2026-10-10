import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/station.dart';

void main() {
  test('catalog and archive samples do not claim live telemetry', () {
    final station = SeismicStation.fromMap(<String, dynamic>{
      'station_id': 'ROSC',
      'network': 'CM',
      'country_code': 'CO',
      'latitude': 4.84,
      'longitude': -74.32,
      'access_status': 'public_waveform_verified',
      'metadata_current': true,
    });
    expect(station.availabilityLabel, contains('no confirma emisión en vivo'));
    const historical = SeismicStation(
      id: 'OLD',
      network: 'CM',
      latitude: 4,
      longitude: -74,
      metadataCurrent: false,
    );
    expect(historical.availabilityLabel, contains('histórica'));
    const legacy = SeismicStation(
      id: 'HEL',
      network: 'CM',
      latitude: 6,
      longitude: -75,
    );
    expect(legacy.availabilityLabel, contains('no verificada'));
  });
}
