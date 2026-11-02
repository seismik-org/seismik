import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/seismic_event.dart';

void main() {
  test(
    'associated reports survive offline serialization with distinct scales',
    () {
      final event = SeismicEvent.fromMap({
        'event_id': 'sgc:1',
        'type': 'official_report_update',
        'origin_time': '2026-10-12T12:00:00Z',
        'related_event_ids': ['sgc:1', 'usgs:2'],
        'source_reports': [
          {
            'event_id': 'sgc:1',
            'agency': 'SGC',
            'magnitude': 4.2,
            'magnitude_type': 'ML',
          },
          {
            'event_id': 'usgs:2',
            'agency': 'USGS',
            'magnitude': 4.8,
            'magnitude_type': 'Mw',
          },
        ],
      });
      final cached = SeismicEvent.fromMap(event.toMap());
      expect(cached.sourceReports.length, 2);
      expect(cached.sourceReports[1].magnitude, 4.8);
      expect(cached.sourceReports[0].magnitudeType, 'ML');
      expect(cached.relatedEventIds, ['sgc:1', 'usgs:2']);
      expect(SeismicEvent.fromMap({'event_id': 'old'}).sourceReports, isEmpty);
    },
  );
}
