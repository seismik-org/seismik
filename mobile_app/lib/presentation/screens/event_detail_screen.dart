import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../data/models/seismic_event.dart';
import 'felt_report_screen.dart';
import 'damage_report_screen.dart';

class EventDetailScreen extends StatelessWidget {
  const EventDetailScreen({required this.event, this.onClose, super.key});
  final SeismicEvent event;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    final LatLng epicenter = LatLng(event.latitude ?? 0, event.longitude ?? 0);
    return Scaffold(
      appBar: AppBar(
        leading: onClose == null
            ? null
            : IconButton(icon: const Icon(Icons.close), onPressed: onClose),
        title: const Text('Reporte oficial'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(18),
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                event.magnitude?.toStringAsFixed(1) ?? '—',
                style: const TextStyle(
                  fontSize: 82,
                  fontWeight: FontWeight.w900,
                  height: 1,
                ),
              ),
              const Padding(
                padding: EdgeInsets.only(top: 12, left: 4),
                child: Text(
                  'M_w',
                  style: TextStyle(fontSize: 22, color: Colors.white70),
                ),
              ),
            ],
          ),
          Text(
            event.place ?? 'Epicentro en revisión',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: <Widget>[
              _Metric(
                icon: Icons.vertical_align_bottom,
                label: '${event.depthKm?.toStringAsFixed(1) ?? '—'} km',
                caption: 'Profundidad',
              ),
              _Metric(
                icon: Icons.public,
                label: event.agency ?? '—',
                caption: 'Entidad emisora',
              ),
              _Metric(
                icon: Icons.schedule,
                label: _time(event.detectedAt),
                caption: 'Hora UTC',
              ),
            ],
          ),
          const SizedBox(height: 22),
          if (event.latitude != null && event.longitude != null)
            SizedBox(
              height: 360,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(22),
                child: FlutterMap(
                  options: MapOptions(initialCenter: epicenter, initialZoom: 7),
                  children: <Widget>[
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.seismik.app',
                    ),
                    MarkerLayer(
                      markers: <Marker>[
                        Marker(
                          point: epicenter,
                          width: 64,
                          height: 64,
                          child: const Icon(
                            Icons.crisis_alert,
                            size: 56,
                            color: Colors.redAccent,
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
          const SizedBox(height: 18),
          FilledButton.tonalIcon(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => FeltReportScreen(event: event),
              ),
            ),
            icon: const Icon(Icons.waves),
            label: const Text('Informar si lo sentí'),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => DamageReportScreen(event: event),
              ),
            ),
            icon: const Icon(Icons.report_problem),
            label: const Text('Reportar daños'),
          ),
        ],
      ),
    );
  }

  static String _time(DateTime value) =>
      value.toUtc().toIso8601String().substring(11, 19);
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.icon,
    required this.label,
    required this.caption,
  });
  final IconData icon;
  final String label;
  final String caption;

  @override
  Widget build(BuildContext context) => Container(
    width: 155,
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: 0.07),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icon, color: const Color(0xFF1ECB7B)),
        const SizedBox(height: 10),
        Text(
          label,
          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
        ),
        Text(caption, style: const TextStyle(color: Colors.white60)),
      ],
    ),
  );
}
