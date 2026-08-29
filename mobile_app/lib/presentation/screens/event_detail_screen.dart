import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/seismic_event.dart';
import 'felt_report_screen.dart';
import 'damage_report_screen.dart';

class EventDetailScreen extends StatelessWidget {
  const EventDetailScreen({required this.event, this.onClose, super.key});
  final SeismicEvent event;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
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
              Padding(
                padding: EdgeInsets.only(top: 12, left: 4),
                child: Text(
                  event.magnitudeType == null
                      ? 'M'
                      : 'M${event.magnitudeType!.toLowerCase()}',
                  style: TextStyle(
                    fontSize: 22,
                    color: colors.onSurfaceVariant,
                  ),
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
              if (event.reviewStatus != null)
                _Metric(
                  icon: Icons.verified_outlined,
                  label: event.reviewStatus!,
                  caption: 'Estado oficial',
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
                child: GoogleMap(
                  initialCameraPosition: CameraPosition(
                    target: epicenter,
                    zoom: 7,
                  ),
                  markers: <Marker>{
                    Marker(
                      markerId: MarkerId(event.id),
                      position: epicenter,
                      infoWindow: InfoWindow(
                        title: event.place ?? 'Epicentro',
                        snippet: event.agency,
                      ),
                      icon: BitmapDescriptor.defaultMarkerWithHue(
                        BitmapDescriptor.hueRed,
                      ),
                    ),
                  },
                  zoomControlsEnabled: false,
                  mapToolbarEnabled: false,
                ),
              ),
            ),
          const SizedBox(height: 18),
          if (event.tsunami == true) ...<Widget>[
            Card(
              color: colors.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'La fuente marcó este evento con información de tsunami. Consulta inmediatamente a la autoridad local.',
                  style: TextStyle(
                    color: colors.onErrorContainer,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (event.officialUrl != null)
            OutlinedButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(event.officialUrl!),
                mode: LaunchMode.externalApplication,
              ),
              icon: const Icon(Icons.open_in_new_rounded),
              label: Text(
                'Abrir fuente oficial${event.attribution == null ? '' : ' · ${event.attribution}'}',
              ),
            ),
          const SizedBox(height: 8),
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
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      width: 155,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icon, color: colors.primary),
          const SizedBox(height: 10),
          Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
          ),
          Text(caption, style: TextStyle(color: colors.onSurfaceVariant)),
        ],
      ),
    );
  }
}
