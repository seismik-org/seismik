import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../data/models/seismic_event.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
import '../widgets/status_pill.dart';
import 'event_detail_screen.dart';

class MonitorScreen extends StatelessWidget {
  const MonitorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    final MobileSettings settings = context.watch<MobileSettings>();
    final LatLng center = state.position == null
        ? const LatLng(4.65, -74.05)
        : LatLng(state.position!.latitude, state.position!.longitude);
    final Set<Marker> markers = <Marker>{
      for (final station in state.stations)
        Marker(
          markerId: MarkerId('${station.network}.${station.id}'),
          position: LatLng(station.latitude, station.longitude),
          infoWindow: InfoWindow(
            title: '${station.network}.${station.id}',
            snippet: 'Estación sísmica',
          ),
          icon: BitmapDescriptor.defaultMarkerWithHue(
            BitmapDescriptor.hueAzure,
          ),
        ),
      for (final event in state.recentEvents.take(100))
        if (event.latitude != null && event.longitude != null)
          Marker(
            markerId: MarkerId('event.${event.id}'),
            position: LatLng(event.latitude!, event.longitude!),
            infoWindow: InfoWindow(
              title:
                  'M ${event.magnitude?.toStringAsFixed(1) ?? '—'} · ${_shortAgency(event)}',
              snippet: event.place ?? 'Evento oficial',
            ),
            icon: BitmapDescriptor.defaultMarkerWithHue(
              event.magnitude != null && event.magnitude! >= 5
                  ? BitmapDescriptor.hueRed
                  : BitmapDescriptor.hueOrange,
            ),
          ),
    };
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: <Widget>[
            Image.asset(
              'assets/images/seismik_logo.png',
              width: 38,
              height: 38,
            ),
            const SizedBox(width: 10),
            const Text(
              'SEISMIK',
              style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2),
            ),
          ],
        ),
        actions: <Widget>[
          IconButton(
            onPressed: state.refreshNetworkData,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Stack(
        children: <Widget>[
          GoogleMap(
            initialCameraPosition: CameraPosition(target: center, zoom: 5.8),
            markers: markers,
            myLocationEnabled: state.position != null,
            myLocationButtonEnabled: state.position != null,
            compassEnabled: false,
            zoomControlsEnabled: false,
            mapToolbarEnabled: false,
          ),
          DraggableScrollableSheet(
            initialChildSize: 0.34,
            minChildSize: 0.16,
            maxChildSize: 0.82,
            builder: (context, controller) => Material(
              elevation: 14,
              color: Theme.of(context).colorScheme.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(28),
              ),
              child: RefreshIndicator(
                onRefresh: state.refreshNetworkData,
                child: ListView(
                  controller: controller,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
                  children: <Widget>[
                    Center(
                      child: Container(
                        width: 42,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.outlineVariant,
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    StatusPill(online: state.networkOnline),
                    const SizedBox(height: 12),
                    Text(
                      'Historial de sismos',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w900),
                    ),
                    Text(
                      '${settings.historyDays} días · M ≥ ${settings.minimumHistoryMagnitude.toStringAsFixed(1)} · ${settings.historySources.map(_sourceLabel).join(' + ')}',
                    ),
                    if (state.statusMessage != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          state.statusMessage!,
                          style: const TextStyle(color: Colors.orangeAccent),
                        ),
                      ),
                    const SizedBox(height: 14),
                    if (state.recentEvents.isEmpty)
                      const Card(
                        child: Padding(
                          padding: EdgeInsets.all(18),
                          child: Text(
                            'Aún no hay reportes oficiales sincronizados.',
                          ),
                        ),
                      )
                    else
                      ...state.recentEvents.map(
                        (event) => _EventTile(event: event),
                      ),
                    const SizedBox(height: 8),
                    Text(
                      'Arrastra esta barra para explorar los sismos; mueve y acerca el mapa libremente.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _sourceLabel(String id) => switch (id) {
    'sgc_colombia' => 'SGC',
    'usgs_global' => 'USGS',
    'igp_peru' => 'IGP',
    'ingv_italy' => 'INGV',
    'geonet_new_zealand' => 'GeoNet',
    'bmkg_indonesia' => 'BMKG',
    'jma_japan' => 'JMA',
    _ => id,
  };

  static String _shortAgency(SeismicEvent event) =>
      _sourceLabel(event.sourceId ?? event.agency ?? 'Oficial');
}

class _EventTile extends StatelessWidget {
  const _EventTile({required this.event});
  final SeismicEvent event;

  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      leading: CircleAvatar(
        backgroundColor: Theme.of(context).colorScheme.errorContainer,
        foregroundColor: Theme.of(context).colorScheme.onErrorContainer,
        child: Text(event.magnitude?.toStringAsFixed(1) ?? '?'),
      ),
      title: Text(event.place ?? 'Evento sísmico'),
      subtitle: Text(
        <String>[
          _agencyLabel(event),
          _formatTime(event.detectedAt),
          '${event.depthKm?.toStringAsFixed(0) ?? '—'} km',
        ].join(' · '),
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => EventDetailScreen(event: event),
        ),
      ),
    ),
  );

  static String _agencyLabel(SeismicEvent event) => switch (event.sourceId) {
    'sgc_colombia' => 'SGC',
    'usgs_global' => 'USGS',
    'igp_peru' => 'IGP',
    'ingv_italy' => 'INGV',
    'geonet_new_zealand' => 'GeoNet',
    'bmkg_indonesia' => 'BMKG',
    'jma_japan' => 'JMA',
    _ => event.agency ?? 'Fuente oficial',
  };

  static String _formatTime(DateTime utc) {
    final DateTime value = utc.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(value.day)}/${two(value.month)} ${two(value.hour)}:${two(value.minute)}';
  }
}
