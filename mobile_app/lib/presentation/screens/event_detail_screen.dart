import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../core/platform.dart';
import '../../data/models/seismic_event.dart';
import '../../services/in_app_browser.dart';
import '../widgets/adaptive.dart';
import '../widgets/open_in_maps_button.dart';
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
    return AdaptiveScreen(
      title: event.isPreliminary ? 'Reporte preliminar' : 'Reporte oficial',
      onClose: onClose,
      child: ListView(
        padding: const EdgeInsets.all(18),
        children: <Widget>[
          if (event.isPreliminary) ...<Widget>[
            Card(
              color: Colors.deepPurple.withValues(alpha: 0.16),
              child: const Padding(
                padding: EdgeInsets.all(14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Icon(Icons.science_outlined, color: Colors.deepPurple),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'SEISMIK / SEEDLINK · PRELIMINAR\n'
                        'Detección automática multiestación. No es una confirmación oficial. Las ondas se miden en cada estación, pero una magnitud solo se mostrará tras calibrar su respuesta instrumental y validarla científicamente.',
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
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
                label: event.isPreliminary
                    ? '${event.stationCount ?? event.stations.length} estaciones'
                    : '${event.depthKm?.toStringAsFixed(1) ?? '—'} km',
                caption: event.isPreliminary ? 'Coincidencia' : 'Profundidad',
              ),
              if (event.reviewStatus != null)
                _Metric(
                  icon: Icons.verified_outlined,
                  label: event.reviewStatus!,
                  caption: 'Estado oficial',
                ),
              _Metric(
                icon: Icons.public,
                label: event.isPreliminary
                    ? 'Seismik / SeedLink'
                    : event.agency ?? '—',
                caption: event.isPreliminary ? 'Proveedor' : 'Entidad emisora',
              ),
              _Metric(
                icon: Icons.schedule,
                label: _time(event.detectedAt),
                caption: 'Hora UTC',
              ),
              if (event.isPreliminary && event.coincidenceWindowSeconds != null)
                _Metric(
                  icon: Icons.timer_outlined,
                  label:
                      '${event.coincidenceWindowSeconds!.toStringAsFixed(1)} s',
                  caption: 'Ventana de coincidencia',
                ),
              if (event.isPreliminary && event.waveStrengthIndex != null)
                _Metric(
                  icon: Icons.graphic_eq_rounded,
                  label: event.waveStrengthIndex!.toStringAsFixed(2),
                  caption: 'Índice de onda (S/R)',
                ),
            ],
          ),
          if (event.isPreliminary) ...<Widget>[
            const SizedBox(height: 16),
            Text(
              event.algorithm ?? 'STA/LTA con coincidencia multiestación',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            if (event.zoneId != null || event.countryCodes.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  <String>[
                    if (event.zoneId != null) 'Zona: ${event.zoneId}',
                    if (event.countryCodes.isNotEmpty)
                      'Países: ${event.countryCodes.join(', ')}',
                  ].join(' · '),
                ),
              ),
            if (event.magnitudeEstimateStatus == 'pending_station_calibration')
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'Magnitud aproximada: pendiente de calibración por estación. '
                  'Mostrar un número sin esa calibración sería engañoso.',
                ),
              ),
            if (event.magnitudeEstimateStatus == 'validated_preliminary' &&
                event.magnitude != null)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'M~ es una estimación de red calibrada; puede cambiar cuando llegue el informe oficial.',
                ),
              ),
            const SizedBox(height: 8),
            ...event.stations.map(
              (station) => ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.sensors_outlined),
                title: Text(station.stationId),
                subtitle: Text(
                  '${station.providerId}${station.countryCode == null ? '' : ' · ${station.countryCode}'} · '
                  '${_time(station.triggerTime)} UTC',
                ),
                trailing: Text(
                  <String>[
                    'STA/LTA ${station.staLtaRatio.toStringAsFixed(1)}',
                    if (station.peakAmplitudeCounts != null)
                      'Pico ${station.peakAmplitudeCounts!.toStringAsFixed(1)} c',
                  ].join('\n'),
                  textAlign: TextAlign.end,
                ),
              ),
            ),
          ],
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
                        event.isPreliminary
                            ? BitmapDescriptor.hueViolet
                            : BitmapDescriptor.hueRed,
                      ),
                    ),
                  },
                  zoomControlsEnabled: false,
                  mapToolbarEnabled: false,
                ),
              ),
            ),
          const SizedBox(height: 12),
          OpenInMapsButton(event: event),
          const SizedBox(height: 6),
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
            AdaptiveButton(
              kind: AdaptiveButtonKind.tinted,
              icon: Icons.open_in_new_rounded,
              onPressed: () => openWebLink(Uri.parse(event.officialUrl!)),
              label:
                  'Abrir fuente oficial${event.attribution == null ? '' : ' · ${event.attribution}'}',
            ),
          const SizedBox(height: 10),
          AdaptiveButton(
            kind: AdaptiveButtonKind.tinted,
            icon: Icons.waves,
            label: 'Informar si lo sentí',
            onPressed: () => Navigator.of(context).push(
              adaptiveRoute<void>(
                (_) => FeltReportScreen(event: event),
                title: 'Sismo sentido',
              ),
            ),
          ),
          const SizedBox(height: 10),
          AdaptiveButton(
            kind: AdaptiveButtonKind.destructive,
            icon: Icons.report_problem,
            label: 'Reportar daños',
            onPressed: () => Navigator.of(context).push(
              adaptiveRoute<void>(
                (_) => DamageReportScreen(event: event),
                title: 'Daños',
              ),
            ),
          ),
          SizedBox(height: usesCupertino ? 28 : 8),
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
