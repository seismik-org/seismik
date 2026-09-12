import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../data/models/seismic_event.dart';
import '../../data/models/station.dart';

/// Agrupa las ~1.800 estaciones de la red.
///
/// Sin agrupar, el mapa nativo dibuja cada pin en cada movimiento de cámara; en
/// teléfonos modestos eso basta para que el mapa se trabe. Agrupadas, sólo se
/// ven los pines individuales al acercarse.
final ClusterManager stationClusterManager = ClusterManager(
  clusterManagerId: const ClusterManagerId('stations'),
);

/// Sismos dibujados como pin individual; el resto sigue en la lista.
const int maxEventMarkers = 100;

Set<Marker> buildMapMarkers({
  required List<SeismicStation> stations,
  required List<SeismicEvent> events,
  required void Function(SeismicEvent event) onEventTap,
  required String Function(SeismicEvent event) eventTitle,
  required String Function(SeismicEvent event) eventSnippet,
}) {
  final BitmapDescriptor stationIcon = BitmapDescriptor.defaultMarkerWithHue(
    BitmapDescriptor.hueAzure,
  );
  final BitmapDescriptor preliminaryIcon =
      BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueViolet);
  final BitmapDescriptor strongIcon = BitmapDescriptor.defaultMarkerWithHue(
    BitmapDescriptor.hueRed,
  );
  final BitmapDescriptor moderateIcon = BitmapDescriptor.defaultMarkerWithHue(
    BitmapDescriptor.hueOrange,
  );
  final ClusterManagerId stationCluster =
      stationClusterManager.clusterManagerId;

  return <Marker>{
    for (final SeismicStation station in stations)
      Marker(
        markerId: MarkerId('${station.network}.${station.id}'),
        position: LatLng(station.latitude, station.longitude),
        clusterManagerId: stationCluster,
        infoWindow: InfoWindow(
          title: '${station.network}.${station.id}',
          snippet: 'Estación sísmica',
        ),
        icon: stationIcon,
      ),
    for (final SeismicEvent event in events.take(maxEventMarkers))
      if (event.latitude != null && event.longitude != null)
        Marker(
          markerId: MarkerId('event.${event.id}'),
          position: LatLng(event.latitude!, event.longitude!),
          onTap: () => onEventTap(event),
          infoWindow: InfoWindow(
            title: eventTitle(event),
            snippet: eventSnippet(event),
          ),
          icon: event.isPreliminary
              ? preliminaryIcon
              : event.magnitude != null && event.magnitude! >= 5
              ? strongIcon
              : moderateIcon,
        ),
  };
}

/// Conserva el conjunto de marcadores mientras las listas no cambien.
///
/// El mapa compara el conjunto nuevo con el anterior y envía las diferencias
/// al lado nativo. Construir ~1.900 marcadores nuevos en cada cambio del
/// estado (incluso al tocar el mapa) obligaba a compararlos todos otra vez.
/// El estado sólo reemplaza las listas cuando llegan datos distintos, así que
/// comparar su identidad es suficiente.
class MarkerSetCache {
  List<SeismicStation>? _stations;
  List<SeismicEvent>? _events;
  Set<Marker>? _markers;

  Set<Marker> resolve({
    required List<SeismicStation> stations,
    required List<SeismicEvent> events,
    required Set<Marker> Function() build,
  }) {
    final Set<Marker>? cached = _markers;
    if (cached != null &&
        identical(stations, _stations) &&
        identical(events, _events)) {
      return cached;
    }
    _stations = stations;
    _events = events;
    return _markers = build();
  }
}
