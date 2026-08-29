import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../data/models/seismic_event.dart';
import '../../state/seismik_state.dart';
import '../widgets/status_pill.dart';
import 'event_detail_screen.dart';

class MonitorScreen extends StatelessWidget {
  const MonitorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
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
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 116),
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
            ],
          ),
        ),
      ),
    );
  }
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
        '${event.agency ?? 'Fuente pendiente'} · ${event.depthKm?.toStringAsFixed(0) ?? '—'} km',
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => EventDetailScreen(event: event),
        ),
      ),
    ),
  );
}
