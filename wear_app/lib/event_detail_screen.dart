import 'package:flutter/material.dart';

import 'event.dart';
import 'rotary.dart';

/// Detalle de un sismo en la muñeca: la magnitud de cada organización con su
/// propia escala, para que una diferencia entre ML, Mw o mb no parezca un error.
///
/// Sólo informa: no emite alarmas ni cambia lo que decide el teléfono.
class WearEventDetailScreen extends StatefulWidget {
  const WearEventDetailScreen({
    required this.event,
    required this.accent,
    super.key,
  });

  final WearEvent event;

  /// Color semántico de la magnitud, el mismo de la lista.
  final Color accent;

  @override
  State<WearEventDetailScreen> createState() => _WearEventDetailScreenState();
}

class _WearEventDetailScreenState extends State<WearEventDetailScreen> {
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final WearEvent event = widget.event;
    final ColorScheme colors = Theme.of(context).colorScheme;
    final List<WearSourceReport> reports = event.sourceReports;
    final TextStyle muted = TextStyle(
      color: colors.onSurfaceVariant,
      fontSize: 11,
      height: 1.3,
    );
    return Scaffold(
      body: SafeArea(
        child: RotaryScroll(
          controller: _scroll,
          child: ListView(
            controller: _scroll,
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 28),
            children: <Widget>[
              Text(
                event.magnitudeLabel,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: widget.accent,
                  fontSize: 34,
                  height: 1,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.2,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                event.place ?? 'Ubicación por confirmar',
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: 13,
                  height: 1.2,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                <String>[
                  event.ago(),
                  if (event.depthKm != null)
                    '${event.depthKm!.round()} km de profundidad',
                ].join(' · '),
                textAlign: TextAlign.center,
                style: muted,
              ),
              const SizedBox(height: 14),
              Text(
                'Magnitudes por organización',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Cada una conserva su valor y su escala. No se promedian.',
                textAlign: TextAlign.center,
                style: muted,
              ),
              const SizedBox(height: 10),
              if (reports.isEmpty)
                _ReportTile(
                  report: WearSourceReport(
                    agency: event.agency ?? 'Fuente',
                    magnitude: event.magnitude,
                    magnitudeText: event.magnitude?.toString(),
                  ),
                )
              else
                for (final WearSourceReport report in reports)
                  _ReportTile(report: report),
            ],
          ),
        ),
      ),
    );
  }
}

class _ReportTile extends StatelessWidget {
  const _ReportTile({required this.report});

  final WearSourceReport report;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final String detail = <String>[
      if (report.magnitudeType != null) report.magnitudeType!,
      report.reviewStatus ?? 'Sin estado de revisión',
    ].join(' · ');
    return Semantics(
      container: true,
      label: '${report.agency}: ${report.valueLabel}. $detail',
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: colors.surfaceContainer,
          borderRadius: BorderRadius.circular(16),
        ),
        child: ExcludeSemantics(
          child: Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      report.agency,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: colors.onSurface,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      detail,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: colors.onSurfaceVariant,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                report.valueLabel,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: report.magnitude == null ? 11 : 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
