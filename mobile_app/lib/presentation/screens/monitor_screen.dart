import 'package:flutter/cupertino.dart'
    show CupertinoIcons, CupertinoPageRoute, CupertinoPageScaffold;
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../../data/models/seismic_event.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
import '../widgets/liquid_glass.dart';
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
    final SeismikState state = context.watch<SeismikState>();
    final MobileSettings settings = context.watch<MobileSettings>();
    final LatLng center = state.position == null
        ? const LatLng(4.65, -74.05)
        : LatLng(state.position!.latitude, state.position!.longitude);
    final Widget content = Stack(
        children: <Widget>[
          GoogleMap(
            initialCameraPosition: CameraPosition(target: center, zoom: 5.8),
            markers: _markers(state),
            onTap: (_) => state.selectEvent(null),
            myLocationEnabled: state.position != null,
            myLocationButtonEnabled: state.position != null,
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
              child: Builder(
                builder: (context) => ListView(
                  controller: controller,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
                  children: <Widget>[
                    const _SheetHandle(),
                    const SizedBox(height: 12),
                    StatusPill(online: state.networkOnline),
                    if (state.pendingReportCount > 0 ||
                        state.syncMessage != null) ...<Widget>[
                      const SizedBox(height: 8),
                      _SyncBanner(
                        pending: state.pendingReportCount,
                        message: state.syncMessage,
                        onRetry: state.flushPendingReports,
                      ),
                    ],
                    const SizedBox(height: 12),
                    Text(
                      'Historial de sismos',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w900),
                    ),
                    Text(
                      '${settings.historyDays} días · M ≥ '
                      '${settings.minimumHistoryMagnitude.toStringAsFixed(1)} · '
                      '${settings.historySources.map(_sourceLabel).join(' + ')}',
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
                          child: Text('Aún no hay reportes sincronizados.'),
                        ),
                      )
                    else
                      ...state.recentEvents.map(
                        (event) => _EventTile(
                          event: event,
                          onOpenDetail: () => _openDetail(event),
                        ),
                      ),
                    if (state.recentEvents.any((event) => event.isPreliminary))
                      const _CalibrationStatusCard(),
                    const SizedBox(height: 8),
                    Text(
                      'Arrastra esta barra para explorar los sismos; mueve y '
                      'acerca el mapa libremente. Toca un sismo para abrir su '
                      'detalle del reporte.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
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

  Set<Marker> _markers(SeismikState state) => <Marker>{
    for (final station in state.stations)
      Marker(
        markerId: MarkerId('${station.network}.${station.id}'),
        position: LatLng(station.latitude, station.longitude),
        infoWindow: InfoWindow(
          title: '${station.network}.${station.id}',
          snippet: 'Estación sísmica',
        ),
        icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure),
      ),
    for (final event in state.recentEvents.take(100))
      if (event.latitude != null && event.longitude != null)
        Marker(
          markerId: MarkerId('event.${event.id}'),
          position: LatLng(event.latitude!, event.longitude!),
          onTap: () => _openDetail(event),
          infoWindow: InfoWindow(
            title:
                'M ${event.magnitude?.toStringAsFixed(1) ?? '—'} · '
                '${_shortAgency(event)}',
            snippet:
                event.place ??
                (event.isPreliminary
                    ? 'Candidato preliminar'
                    : 'Evento oficial'),
          ),
          icon: BitmapDescriptor.defaultMarkerWithHue(
            event.isPreliminary
                ? BitmapDescriptor.hueViolet
                : event.magnitude != null && event.magnitude! >= 5
                ? BitmapDescriptor.hueRed
                : BitmapDescriptor.hueOrange,
          ),
        ),
  };

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

/// Identidad y acción de recarga flotando sobre el mapa en iPhone.
class _IosMapHeader extends StatelessWidget {
  const _IosMapHeader({required this.onRefresh});

  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) => SafeArea(
    bottom: false,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Row(
        children: <Widget>[
          LiquidGlass(
            borderRadius: 20,
            padding: const EdgeInsets.fromLTRB(12, 8, 16, 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Image.asset(
                  'assets/images/seismik_logo.png',
                  width: 26,
                  height: 26,
                ),
                const SizedBox(width: 8),
                const Text(
                  'SEISMIK',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.6,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
          ),
          const Spacer(),
          LiquidGlass(
            borderRadius: 20,
            child: Semantics(
              button: true,
              label: 'Actualizar historial',
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onRefresh,
                child: const SizedBox(
                  width: 44,
                  height: 40,
                  child: Icon(CupertinoIcons.arrow_clockwise, size: 20),
                ),
              ),
            ),
          ),
        ],
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
