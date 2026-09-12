import 'package:flutter_test/flutter_test.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/data/models/station.dart';
import 'package:seismik/presentation/widgets/map_markers.dart';

List<SeismicStation> stations(int count) => List<SeismicStation>.generate(
  count,
  (index) => SeismicStation(
    id: 'S$index',
    network: 'CM',
    latitude: 4 + index / 1000,
    longitude: -74 - index / 1000,
  ),
  growable: false,
);

SeismicEvent event(String id, {double? latitude = 4.6}) =>
    SeismicEvent.fromMap(<String, dynamic>{
      'event_id': id,
      'type': 'official_report_update',
      'origin_time': '2026-09-12T12:00:00Z',
      'latitude': latitude,
      'longitude': latitude == null ? null : -74.1,
      'magnitude': 4.2,
    });

Set<Marker> markersFor(List<SeismicStation> s, List<SeismicEvent> e) =>
    buildMapMarkers(
      stations: s,
      events: e,
      onEventTap: (_) {},
      eventTitle: (event) => event.id,
      eventSnippet: (_) => '',
    );

void main() {
  test('las estaciones van al agrupador y los sismos quedan sueltos', () {
    final Set<Marker> markers = markersFor(
      stations(1837),
      <SeismicEvent>[event('a'), event('b')],
    );
    final ClusterManagerId cluster = stationClusterManager.clusterManagerId;

    expect(
      markers.where((marker) => marker.clusterManagerId == cluster),
      hasLength(1837),
    );
    final Iterable<Marker> events = markers.where(
      (marker) => marker.markerId.value.startsWith('event.'),
    );
    expect(events, hasLength(2));
    expect(events.map((marker) => marker.clusterManagerId), everyElement(isNull));
  });

  test('se dibujan como máximo 100 sismos y sólo los que tienen coordenadas', () {
    final Set<Marker> markers = markersFor(const <SeismicStation>[], <SeismicEvent>[
      event('sin-coordenadas', latitude: null),
      for (int index = 0; index < 150; index++) event('e$index'),
    ]);

    expect(markers, hasLength(maxEventMarkers - 1));
    expect(
      markers.map((marker) => marker.markerId.value),
      isNot(contains('event.sin-coordenadas')),
    );
  });

  test('con las mismas listas se reutiliza el conjunto sin reconstruirlo', () {
    final MarkerSetCache cache = MarkerSetCache();
    final List<SeismicStation> network = stations(10);
    final List<SeismicEvent> history = <SeismicEvent>[event('a')];
    int builds = 0;
    Set<Marker> resolve(List<SeismicStation> s, List<SeismicEvent> e) =>
        cache.resolve(
          stations: s,
          events: e,
          build: () {
            builds++;
            return markersFor(s, e);
          },
        );

    final Set<Marker> first = resolve(network, history);
    final Set<Marker> second = resolve(network, history);
    expect(identical(first, second), isTrue);
    expect(builds, 1);

    // El estado sólo entrega una lista nueva cuando llegan datos nuevos.
    resolve(network, <SeismicEvent>[event('a'), event('b')]);
    expect(builds, 2);
  });
}
