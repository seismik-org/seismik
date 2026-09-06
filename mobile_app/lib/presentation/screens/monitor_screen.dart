import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../data/models/seismic_event.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
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
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => EventDetailScreen(event: event)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    final MobileSettings settings = context.watch<MobileSettings>();
    final LatLng center = state.position == null
        ? const LatLng(4.65, -74.05)
        : LatLng(state.position!.latitude, state.position!.longitude);
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
      body: Stack(
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
            builder: (context, controller) => Material(
              elevation: 14,
              color: Theme.of(context).colorScheme.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(28),
              ),
              child: RefreshIndicator(
                onRefresh: state.refreshNetworkData,
                child: ListView(
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
      ),
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
