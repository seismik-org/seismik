import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../data/models/seismic_event.dart';
import '../../state/seismik_state.dart';
import '../widgets/status_pill.dart';
import 'event_detail_screen.dart';
import 'felt_report_screen.dart';
import 'damage_report_screen.dart';

class MonitorScreen extends StatelessWidget {
  const MonitorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    final LatLng center = state.position == null
        ? const LatLng(4.65, -74.05)
        : LatLng(state.position!.latitude, state.position!.longitude);
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'SEISMIK',
          style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 3),
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
              _ReportingActions(
                event:
                    state.officialEvent ??
                    (state.recentEvents.isEmpty
                        ? null
                        : state.recentEvents.first),
              ),
              const SizedBox(height: 16),
              SizedBox(
                height: 380,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: FlutterMap(
                    options: MapOptions(
                      initialCenter: center,
                      initialZoom: 5.8,
                    ),
                    children: <Widget>[
                      TileLayer(
                        urlTemplate:
                            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.seismik.app',
                      ),
                      MarkerLayer(
                        markers: <Marker>[
                          ...state.stations.map(
                            (station) => Marker(
                              point: LatLng(
                                station.latitude,
                                station.longitude,
                              ),
                              width: 30,
                              height: 30,
                              child: Tooltip(
                                message: '${station.network}.${station.id}',
                                child: Icon(
                                  Icons.sensors,
                                  color: colors.primary,
                                  size: 22,
                                ),
                              ),
                            ),
                          ),
                          if (state.position != null)
                            Marker(
                              point: center,
                              width: 32,
                              height: 32,
                              child: Icon(
                                Icons.my_location,
                                color: colors.tertiary,
                              ),
                            ),
                        ],
                      ),
                      const RichAttributionWidget(
                        attributions: <SourceAttribution>[
                          TextSourceAttribution('OpenStreetMap contributors'),
                        ],
                      ),
                    ],
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

class _ReportingActions extends StatelessWidget {
  const _ReportingActions({required this.event});
  final SeismicEvent? event;

  @override
  Widget build(BuildContext context) => Row(
    children: <Widget>[
      Expanded(
        child: FilledButton.tonalIcon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => FeltReportScreen(event: event),
            ),
          ),
          icon: const Icon(Icons.waves),
          label: const Text('¿Lo sentiste?'),
        ),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: FilledButton.icon(
          style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => DamageReportScreen(event: event),
            ),
          ),
          icon: const Icon(Icons.report_problem),
          label: const Text('Reportar daños'),
        ),
      ),
    ],
  );
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
