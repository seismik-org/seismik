import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../core/felt_area.dart';
import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../data/models/seismic_event.dart';
import '../../services/in_app_browser.dart';
import '../../state/seismik_state.dart';
import '../widgets/adaptive.dart';
import '../widgets/liquid_glass.dart';
import '../widgets/open_in_maps_button.dart';
import '../widgets/perimeter_circles.dart';
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
    final List<PerimeterRing> rings = feltPerimeter(event);
    final Position? position = context.select<SeismikState, Position?>(
      (s) => s.position,
    );
    return AdaptiveScreen(
      title: event.isPreliminary ? 'Reporte preliminar' : 'Reporte oficial',
      onClose: onClose,
      child: ListView(
        padding: const EdgeInsets.all(18),
        children: <Widget>[
          if (event.isPreliminary) ...<Widget>[
            if (usesCupertino)
              Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: LiquidGlassCard(
                  borderRadius: 18,
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      const Icon(
                        CupertinoIcons.lab_flask,
                        color: SeismikColors.lavender,
                        size: 24,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'SEISMIK / SEEDLINK · PRELIMINAR\n'
                          'Detección automática multiestación. Las ondas se miden en cada estación; la magnitud se mostrará tras calibrar su respuesta instrumental y validarla.',
                          style: TextStyle(
                            fontSize: 13,
                            height: 1.35,
                            color: CupertinoColors.label.resolveFrom(context),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              )
            else
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
          if (usesCupertino) ...<Widget>[
            LiquidGlassCard(
              borderRadius: 22,
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: <Widget>[
                      Text(
                        event.magnitude?.toStringAsFixed(1) ?? '—',
                        style: TextStyle(
                          fontSize: 80,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -2.0,
                          color: SeismikColors.severityColor(
                            event.magnitude,
                            isPreliminary: event.isPreliminary,
                          ),
                          height: 1,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        event.magnitudeType == null
                            ? 'M'
                            : 'M${event.magnitudeType!.toLowerCase()}',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w600,
                          color: CupertinoColors.secondaryLabel.resolveFrom(context),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    event.place ?? 'Epicentro en revisión',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.4,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
          ] else ...<Widget>[
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
                  padding: const EdgeInsets.only(top: 12, left: 4),
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
          ],
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
          if (event.latitude != null && event.longitude != null) ...<Widget>[
            SizedBox(
              height: 360,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(22),
                child: GoogleMap(
                  // El mapa encuadra hasta donde se sintió el sismo.
                  initialCameraPosition: CameraPosition(
                    target: epicenter,
                    zoom: rings.isEmpty
                        ? 7
                        : perimeterZoom(
                            radiusKm: rings.first.radiusKm,
                            latitude: epicenter.latitude,
                            widthPx: MediaQuery.sizeOf(context).width - 36,
                          ),
                  ),
                  circles: perimeterCircles(event),
                  myLocationEnabled: position != null,
                  myLocationButtonEnabled: false,
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
            _PerimeterCard(event: event, rings: rings, position: position),
          ],
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

/// Explica los círculos del mapa: hasta dónde se sintió y cuánto donde estás.
class _PerimeterCard extends StatelessWidget {
  const _PerimeterCard({
    required this.event,
    required this.rings,
    required this.position,
  });

  final SeismicEvent event;
  final List<PerimeterRing> rings;
  final Position? position;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final Position? here = position;
    final double? localIntensity = here == null
        ? null
        : intensityAtPlace(event, here.latitude, here.longitude);
    final double? distanceKm = here == null
        ? null
        : haversineKm(
            event.latitude!,
            event.longitude!,
            here.latitude,
            here.longitude,
          );
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.track_changes_rounded, color: colors.primary),
              const SizedBox(width: 10),
              Text(
                'Perímetro de sacudida',
                style: text.titleMedium?.copyWith(fontWeight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (event.magnitude == null)
            const Text(
              'Sin magnitud todavía no se puede estimar dónde se sintió.',
            )
          else if (rings.isEmpty)
            const Text(
              'Por su magnitud y profundidad no se espera que se haya sentido '
              'en superficie.',
            )
          else
            for (final PerimeterRing ring in rings)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: <Widget>[
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: perimeterColor(
                          ring.intensity,
                        ).withValues(alpha: 0.35),
                        border: Border.all(
                          color: perimeterColor(ring.intensity),
                          width: 2,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '${intensityRoman(ring.intensity)} · ${ring.label}',
                      ),
                    ),
                    Text(
                      _reach(ring.radiusKm),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ],
                ),
              ),
          if (localIntensity != null && distanceKm != null) ...<Widget>[
            const Divider(height: 22),
            Text(
              localIntensity >= feltIntensity
                  ? 'Donde estás (a ${distanceKm.toStringAsFixed(0)} km): '
                        'intensidad ${intensityRoman(localIntensity)}, '
                        'sacudida ${intensityName(localIntensity)}.'
                  : 'Donde estás (a ${distanceKm.toStringAsFixed(0)} km) no se '
                        'espera que se haya sentido.',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            if (localIntensity >= strongIntensity)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text(
                  'Con sacudida fuerte la alarma suena siempre, sin importar '
                  'tu configuración.',
                ),
              ),
          ],
          const SizedBox(height: 10),
          Text(
            'Estimación con modelos de atenuación publicados (Allen 2012; '
            'Zhao 2006 y Worden 2012). La sacudida real cambia con el suelo y '
            'la construcción: si lo sentiste, repórtalo.',
            style: text.bodySmall?.copyWith(color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  static String _reach(double radiusKm) {
    if (radiusKm >= maxFeltRadiusKm) return 'más de 2.000 km';
    return radiusKm < 10
        ? 'hasta ${radiusKm.toStringAsFixed(1)} km'
        : 'hasta ${radiusKm.toStringAsFixed(0)} km';
  }
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
    if (usesCupertino) {
      final Brightness brightness = CupertinoTheme.brightnessOf(context);
      final bool dark = brightness == Brightness.dark;
      return Container(
        width: 155,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: dark
              ? CupertinoColors.systemGrey6.darkColor.withValues(alpha: 0.55)
              : CupertinoColors.white.withValues(alpha: 0.65),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: dark
                ? CupertinoColors.white.withValues(alpha: 0.12)
                : CupertinoColors.white.withValues(alpha: 0.85),
            width: 0.8,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(icon, color: CupertinoColors.activeBlue.resolveFrom(context), size: 22),
            const SizedBox(height: 10),
            Text(
              label,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 16.5,
                letterSpacing: -0.3,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              caption,
              style: TextStyle(
                color: CupertinoColors.secondaryLabel.resolveFrom(context),
                fontSize: 12.5,
              ),
            ),
          ],
        ),
      );
    }
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

