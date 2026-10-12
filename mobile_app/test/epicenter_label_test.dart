import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/epicenter_label.dart';
import 'package:seismik/data/models/seismic_event.dart';

void main() {
  test(
    'uses coordinates, not a misleading source name; preserves provenance',
    () {
      final SeismicEvent event = SeismicEvent.fromMap(<String, dynamic>{
        'event_id': 'sgc:test',
        'type': 'official_report_update',
        'origin_time': '2026-10-11T12:00:00Z',
        'place': 'WRONG REGION',
        'latitude': 4.6534,
        'longitude': -76.6435,
        'magnitude': 4.2,
        'source_id': 'sgc_colombia',
      });
      expect(event.displayPlace, 'Sipí, Chocó');
      expect(event.place, 'WRONG REGION');
      expect(event.toMap()['place'], 'WRONG REGION');
      expect(event.magnitude, 4.2);
    },
  );
  test('municipality and department work entirely offline', () {
    expect(epicenterLabel(null, 4.3758, -73.2155), 'Paratebueno, Cundinamarca');
    expect(epicenterLabel(null, 6.7534, -73.1047), 'Los Santos, Santander');
  });
  test('missing coordinates do not invent an epicenter', () {
    expect(epicenterLabel(null, null, null), 'Epicentro en revisión');
    expect(epicenterLabel(null, double.nan, -74), 'Epicentro en revisión');
    expect(
      epicenterLabel('48 km WSW of Alaska', null, null),
      '48 km al OSO de Alaska',
    );
    expect(epicenterLabel('MESAS - META', null, null), 'Mesas, Meta');
  });
  test('distant events are not labeled with a Colombian municipality', () {
    expect(
      epicenterLabel(null, 40, -120),
      'Epicentro aproximado: 40.00, -120.00',
    );
  });
}
