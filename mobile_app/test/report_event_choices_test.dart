import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/report_event_choices.dart';
import 'package:seismik/data/models/seismic_event.dart';

void main() {
  final now = DateTime.utc(2026, 10, 4, 12);
  SeismicEvent event(
    String id,
    double? latitude, {
    DateTime? date,
    String? source,
  }) => SeismicEvent(
    id: id,
    type: 'official_report_update',
    detectedAt: date ?? now.subtract(const Duration(hours: 1)),
    latitude: latitude,
    longitude: latitude == null ? null : -74,
    sourceId: source,
  );
  test('orders by distance, deduplicates, excludes old/future/drills', () {
    final choices = reportEventChoices(
      <SeismicEvent>[
        event('far', 8),
        event('near', 4.6),
        event('near', 4.6),
        event('unknown-location', null),
        event('old', 4.6, date: now.subtract(const Duration(days: 8))),
        event('future', 4.6, date: now.add(const Duration(minutes: 2))),
        event('drill-test', 4.6),
        event('simulation', 4.6, source: 'simulation'),
      ],
      now: now,
      latitude: 4.6,
      longitude: -74,
    );
    expect(choices.map((e) => e.id), <String>[
      'near',
      'far',
      'unknown-location',
    ]);
    expect(reportEventDistance(choices.first, 4.6, -74), closeTo(0, 0.001));
  });
  test('without GPS orders by time, does not invent distances', () {
    final choices = reportEventChoices(<SeismicEvent>[
      event('older', 4.6, date: now.subtract(const Duration(hours: 2))),
      event('newer', 8),
    ], now: now);
    expect(choices.map((e) => e.id), <String>['newer', 'older']);
    expect(reportEventDistance(choices.first, null, null), isNull);
  });
}
