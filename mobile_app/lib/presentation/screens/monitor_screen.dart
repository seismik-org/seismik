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
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: state.refreshNetworkData,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
            children: <Widget>[
              StatusPill(online: state.networkOnline),
              if (state.statusMessage != null) ...<Widget>[
                const SizedBox(height: 10),
                Text(
                  state.statusMessage!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 14),
              Text(
                'Historial de Sismos',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${settings.historyDays} días · M ≥ ${settings.minimumHistoryMagnitude.toStringAsFixed(1)} · '
                '${settings.historySources.map(_sourceLabel).join(' + ')}',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              SizedBox(
                height: 380,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: GoogleMap(
                    initialCameraPosition: CameraPosition(
                      target: center,
                      zoom: 5.8,
                    ),
                    markers: markers,
                    myLocationEnabled: state.position != null,
                    myLocationButtonEnabled: state.position != null,
                    compassEnabled: false,
                    zoomControlsEnabled: false,
                    mapToolbarEnabled: false,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'Sismos recientes',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 10),
              if (state.recentEvents.isEmpty)
                const Card(
                  child: Padding(
                    padding: EdgeInsets.all(18),
                    child: Text('Aún no hay reportes oficiales sincronizados.'),
                  ),
                )
              else
                ...state.recentEvents.map((event) => _EventTile(event: event)),
              if (state.recentEvents.isNotEmpty) ...<Widget>[
                const SizedBox(height: 8),
                Text(
                  'Datos atribuidos a las organizaciones indicadas. Abre cada evento para consultar la fuente oficial.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
        ),
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
