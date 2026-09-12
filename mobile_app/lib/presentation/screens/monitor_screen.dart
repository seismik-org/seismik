import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../data/models/seismic_event.dart';
import '../../data/models/station.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
import '../widgets/liquid_glass.dart';
import '../widgets/map_markers.dart';
import '../widgets/status_pill.dart';
import 'event_detail_screen.dart';


/// Historial de sismos como mapa interactivo con panel inferior deslizable.
///
/// El mapa ocupa la pantalla completa y nunca queda bloqueado: la hoja inferior
/// se arrastra entre tres posiciones fijas y, al tocar un marcador, la lista se
/// desplaza al evento sin tapar el epicentro.
class MonitorScreen extends StatefulWidget {
  const MonitorScreen({super.key});

  @override
  State<MonitorScreen> createState() => _MonitorScreenState();
}

class _MonitorScreenState extends State<MonitorScreen> {
  static const double _collapsed = 0.16;
  static const double _resting = 0.36;
  static const double _expanded = 0.86;

  final DraggableScrollableController _sheet = DraggableScrollableController();
  final MarkerSetCache _markerCache = MarkerSetCache();
  static final Set<ClusterManager> _clusterManagers = <ClusterManager>{
    stationClusterManager,
  };
  @override
  void dispose() {
    _sheet.dispose();
    super.dispose();
  }

  void _openDetail(SeismicEvent event) {
    // La transición también es parte de la paridad: iOS empuja desde el borde
    // derecho y permite volver arrastrando.
    Navigator.of(context).push(
      usesCupertino
          ? CupertinoPageRoute<void>(
              title: 'Sismo',
              builder: (_) => EventDetailScreen(event: event),
            )
          : MaterialPageRoute<void>(
              builder: (_) => EventDetailScreen(event: event),
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Cada `select` reconstruye la pantalla sólo cuando cambia ese dato. Con
    // `watch`, cualquier aviso del estado (un reporte en cola, un refresco, un
    // toque en el mapa) volvía a construir el mapa y la lista completa.
    final List<SeismicStation> stations = context
        .select<SeismikState, List<SeismicStation>>((s) => s.stations);
    final List<SeismicEvent> events = context
        .select<SeismikState, List<SeismicEvent>>((s) => s.recentEvents);
    final bool hasPosition = context.select<SeismikState, bool>(
      (s) => s.position != null,
    );
    final bool online = context.select<SeismikState, bool>(
      (s) => s.networkOnline,
    );
    final int pendingReports = context.select<SeismikState, int>(
      (s) => s.pendingReportCount,
    );
    final String? syncMessage = context.select<SeismikState, String?>(
      (s) => s.syncMessage,
    );
    final String? statusMessage = context.select<SeismikState, String?>(
      (s) => s.statusMessage,
    );
    final MobileSettings settings = context.watch<MobileSettings>();
    final SeismikState state = Provider.of<SeismikState>(
      context,
      listen: false,
    );
    final LatLng center = state.position == null
        ? const LatLng(4.65, -74.05)
        : LatLng(state.position!.latitude, state.position!.longitude);
    final Set<Marker> markers = _markerCache.resolve(
      stations: stations,
      events: events,
      build: () => buildMapMarkers(
        stations: stations,
        events: events,
        onEventTap: _openDetail,
        eventTitle: _markerTitle,
        eventSnippet: _markerSnippet,
      ),
    );
    final List<Widget> header = <Widget>[
      const _SheetHandle(),
      const SizedBox(height: 12),
      StatusPill(online: online),
      if (pendingReports > 0 || syncMessage != null) ...<Widget>[
        const SizedBox(height: 8),
        _SyncBanner(
          pending: pendingReports,
          message: syncMessage,
          onRetry: state.flushPendingReports,
        ),
      ],
      const SizedBox(height: 12),
      Text(
        'Historial de sismos',
        style: Theme.of(
          context,
        ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
      ),
      Text(
        '${settings.historyDays} días · M ≥ '
        '${settings.minimumHistoryMagnitude.toStringAsFixed(1)} · '
        '${settings.historySources.map(_sourceLabel).join(' + ')}',
      ),
      if (statusMessage != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            statusMessage,
            style: const TextStyle(color: Colors.orangeAccent),
          ),
        ),
      const SizedBox(height: 14),
      if (events.isEmpty)
        const Card(
          child: Padding(
            padding: EdgeInsets.all(18),
            child: Text('Aún no hay reportes sincronizados.'),
          ),
        ),
    ];
    final List<Widget> footer = <Widget>[
      if (events.any((event) => event.isPreliminary))
        const _CalibrationStatusCard(),
      const SizedBox(height: 8),
      Text(
        'Arrastra esta barra para explorar los sismos; mueve y '
        'acerca el mapa libremente. Toca un sismo para abrir su '
        'detalle del reporte.',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ];
    final Widget content = Stack(
        children: <Widget>[
          GoogleMap(
            initialCameraPosition: CameraPosition(target: center, zoom: 5.8),
            markers: markers,
            clusterManagers: _clusterManagers,
            onTap: (_) => state.selectEvent(null),
            myLocationEnabled: hasPosition,
            myLocationButtonEnabled: hasPosition,
            compassEnabled: false,
            zoomControlsEnabled: false,
            mapToolbarEnabled: false,
            // El padding evita que los controles nativos queden bajo la hoja.
            padding: EdgeInsets.only(
              bottom: MediaQuery.sizeOf(context).height * _collapsed,
            ),
          ),
          DraggableScrollableSheet(
            controller: _sheet,
            initialChildSize: _resting,
            minChildSize: _collapsed,
            maxChildSize: _expanded,
            snap: true,
            snapSizes: const <double>[_collapsed, _resting, _expanded],
            builder: (context, controller) => _SheetSurface(
              onRefresh: state.refreshNetworkData,
              // Sólo se construyen las filas visibles. Con 200 sismos, armarlas
              // todas en cada cambio era trabajo perdido en teléfonos modestos.
              child: ListView.builder(
                controller: controller,
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
                itemCount: header.length + events.length + footer.length,
                itemBuilder: (context, index) {
                  if (index < header.length) return header[index];
                  final int eventIndex = index - header.length;
                  if (eventIndex < events.length) {
                    final SeismicEvent event = events[eventIndex];
                    return _EventTile(
                      event: event,
                      onOpenDetail: () => _openDetail(event),
                    );
                  }
                  return footer[eventIndex - events.length];
                },
              ),
            ),
          ),
        ],
      );

    if (usesCupertino) {
      // En iPhone el mapa llega hasta los bordes y la identidad flota sobre él,
      // como en Mapas de Apple, en vez de perder alto con una barra opaca.
      return CupertinoPageScaffold(
        child: Stack(
          children: <Widget>[
            content,
            _IosMapHeader(onRefresh: state.refreshNetworkData),
          ],
        ),
      );
    }
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
            tooltip: 'Actualizar historial',
            onPressed: state.refreshNetworkData,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: content,
    );
  }

  static String _markerTitle(SeismicEvent event) =>
      'M ${event.magnitude?.toStringAsFixed(1) ?? '—'} · '
      '${_shortAgency(event)}';

  static String _markerSnippet(SeismicEvent event) =>
      event.place ??
      (event.isPreliminary ? 'Candidato preliminar' : 'Evento oficial');

  static String _sourceLabel(String id) => switch (id) {
    'sgc_colombia' => 'SGC',
    'usgs_global' => 'USGS',
    'igp_peru' => 'IGP',
    'ingv_italy' => 'INGV',
    'geonet_new_zealand' => 'GeoNet',
    'bmkg_indonesia' => 'BMKG',
    'jma_japan' => 'JMA',
    'seismik_seedlink_preliminary' => 'SeedLink · preliminar',
    _ => id,
  };

  static String _shortAgency(SeismicEvent event) => event.isPreliminary
      ? 'SeedLink · preliminar'
      : _sourceLabel(event.sourceId ?? event.agency ?? 'Oficial');
}

/// Superficie de la hoja inferior.
///
/// En iPhone es vidrio sobre el mapa; en Android conserva la superficie
/// Material con «pull to refresh», que es el gesto esperado allí. iOS no lo
/// usa aquí porque la hoja arrastra en vertical y los dos gestos competirían.
class _SheetSurface extends StatelessWidget {
  const _SheetSurface({required this.child, required this.onRefresh});

  final Widget child;
  final Future<void> Function() onRefresh;

  static const BorderRadius _corners = BorderRadius.vertical(
    top: Radius.circular(30),
  );

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return LiquidGlass(
        borderRadius: 30,
        borderRadiusGeometry: _corners,
        blurSigma: 30,
        child: child,
      );
    }
    return Material(
      elevation: 14,
      color: Theme.of(context).colorScheme.surface,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
      child: RefreshIndicator(onRefresh: onRefresh, child: child),
    );
  }
}

/// Identidad y acción de recarga flotando sobre el mapa en iPhone con diseño de cápsula de cristal.
class _IosMapHeader extends StatelessWidget {
  const _IosMapHeader({required this.onRefresh});

  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) => SafeArea(
    bottom: false,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      child: LiquidGlass(
        borderRadius: 24,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Row(
          children: <Widget>[
            Image.asset(
              'assets/images/seismik_logo.png',
              width: 26,
              height: 26,
            ),
            const SizedBox(width: 10),
            const Text(
              'SEISMIK',
              style: TextStyle(
                fontWeight: FontWeight.w800,
                letterSpacing: 2.0,
                fontSize: 15,
              ),
            ),
            const Spacer(),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(36),
              onPressed: () {
                unawaited(HapticFeedback.lightImpact());
                unawaited(onRefresh());
              },
              child: const Icon(
                CupertinoIcons.arrow_clockwise,
                size: 19,
                color: CupertinoColors.label,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _SheetHandle extends StatelessWidget {
  const _SheetHandle();

  @override
  Widget build(BuildContext context) => Center(
    child: Container(
      width: 42,
      height: 4,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.outlineVariant,
        borderRadius: BorderRadius.circular(8),
      ),
    ),
  );
}

class _CalibrationStatusCard extends StatelessWidget {
  const _CalibrationStatusCard();

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: LiquidGlassCard(
          borderRadius: 18,
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(
                CupertinoIcons.lab_flask,
                color: SeismikColors.lavender,
                size: 22,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Calibración de magnitud en curso\n'
                  'Seismik conserva pico, ruido y coincidencias para contrastarlos '
                  'con SGC/USGS. Una M~ sólo aparecerá cuando el modelo regional '
                  'esté validado.',
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
      );
    }
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      color: colors.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(Icons.science_outlined, color: colors.onTertiaryContainer),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Calibración de magnitud en curso\n'
                'Seismik conserva pico, ruido y coincidencias para contrastarlos '
                'con SGC/USGS. Una M~ sólo aparecerá cuando el modelo regional '
                'esté validado; los candidatos actuales no son una magnitud oficial.',
                style: TextStyle(color: colors.onTertiaryContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SyncBanner extends StatelessWidget {
  const _SyncBanner({
    required this.pending,
    required this.message,
    required this.onRetry,
  });

  final int pending;
  final String? message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: LiquidGlassCard(
          borderRadius: 18,
          padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
          child: Row(
            children: <Widget>[
              Icon(
                pending > 0
                    ? CupertinoIcons.cloud_upload
                    : CupertinoIcons.cloud_download,
                color: SeismikColors.systemBlue,
                size: 22,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  message ??
                      (pending == 1
                          ? '1 reporte espera conexión.'
                          : '$pending reportes esperan conexión.'),
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w500),
                ),
              ),
              if (pending > 0)
                CupertinoButton(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  minimumSize: Size.zero,
                  onPressed: () {
                    unawaited(HapticFeedback.lightImpact());
                    unawaited(onRetry());
                  },
                  child: const Text(
                    'Reintentar',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
            ],
          ),
        ),
      );
    }
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      color: colors.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
        child: Row(
          children: <Widget>[
            Icon(
              pending > 0
                  ? Icons.cloud_upload_outlined
                  : Icons.cloud_done_outlined,
              color: colors.onSecondaryContainer,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message ??
                    (pending == 1
                        ? '1 reporte espera conexión.'
                        : '$pending reportes esperan conexión.'),
                style: TextStyle(color: colors.onSecondaryContainer),
              ),
            ),
            if (pending > 0)
              TextButton(
                onPressed: () => onRetry(),
                child: const Text('Reintentar'),
              ),
          ],
        ),
      ),
    );
  }
}

class _EventTile extends StatelessWidget {
  const _EventTile({required this.event, required this.onOpenDetail});

  final SeismicEvent event;
  final VoidCallback onOpenDetail;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      final String magText = event.isPreliminary
          ? 'P'
          : (event.magnitude?.toStringAsFixed(1) ?? '—');
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: GlassTile(
          onTap: () {
            unawaited(HapticFeedback.selectionClick());
            onOpenDetail();
          },
          leading: GlassBadge(
            text: magText,
            fontSize: 15,
            isBold: true,
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
            gradient: SeismikColors.severityGradient(
              event.magnitude,
              isPreliminary: event.isPreliminary,
            ),
          ),
          title: Text(
            event.place ?? 'Evento sísmico',
            style: const TextStyle(
              fontSize: 15.5,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.2,
            ),
          ),
          subtitle: Text(
            <String>[
              _agencyLabel(event),
              _formatTime(event.detectedAt),
              '${event.depthKm?.toStringAsFixed(0) ?? '—'} km',
            ].join(' · '),
            style: TextStyle(
              fontSize: 12.5,
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
            ),
          ),
          trailing: const Icon(
            CupertinoIcons.chevron_right,
            size: 16,
            color: CupertinoColors.tertiaryLabel,
          ),
        ),
      );
    }
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: event.isPreliminary
              ? Colors.deepPurple.withValues(alpha: 0.20)
              : colors.errorContainer,
          foregroundColor: event.isPreliminary
              ? Colors.deepPurple
              : colors.onErrorContainer,
          child: Text(
            event.isPreliminary
                ? 'P'
                : event.magnitude?.toStringAsFixed(1) ?? '?',
          ),
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
        onTap: onOpenDetail,
      ),
    );
  }


  static String _agencyLabel(SeismicEvent event) => switch (event.sourceId) {
    'seismik_seedlink_preliminary' => 'Seismik / SeedLink · PRELIMINAR',
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
    return '${two(value.day)}/${two(value.month)} '
        '${two(value.hour)}:${two(value.minute)}';
  }
}
