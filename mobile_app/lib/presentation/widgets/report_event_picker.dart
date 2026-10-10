import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../../core/report_event_choices.dart';
import '../../data/models/seismic_event.dart';
import '../../state/seismik_state.dart';
import 'adaptive.dart';

class ReportEventPicker extends StatefulWidget {
  const ReportEventPicker({
    required this.onSelected,
    this.suggested,
    this.enabled = true,
    super.key,
  });
  final bool enabled;
  final SeismicEvent? suggested;
  final ValueChanged<SeismicEvent> onSelected;

  @override
  State<ReportEventPicker> createState() => _ReportEventPickerState();
}

class _ReportEventPickerState extends State<ReportEventPicker> {
  List<SeismicEvent> _events = <SeismicEvent>[];
  SeismicEvent? _selected;
  double? _latitude;
  double? _longitude;
  bool _loading = false;
  bool _loaded = false;
  String? _warning;

  Future<void> _load() async {
    setState(() => _loading = true);
    final state = context.read<SeismikState>();
    final location = state
        .currentCoordinates()
        .timeout(const Duration(seconds: 8), onTimeout: () => null)
        .catchError((Object _) => null);
    var events = state.recentEvents;
    String? warning;
    try {
      // Independent of monitor magnitude/source preferences: small quakes can be felt.
      events = await state.api.fetchRecentEvents(days: 7, minimumMagnitude: 0);
    } catch (_) {
      warning = 'Sin conexión: se muestran los sismos guardados.';
    }
    final coordinates = await location;
    if (!mounted) return;
    setState(() {
      _latitude = coordinates?.latitude;
      _longitude = coordinates?.longitude;
      _events = reportEventChoices(
        <SeismicEvent>[
          if (widget.suggested != null) widget.suggested!,
          ...events,
        ],
        now: DateTime.now(),
        latitude: _latitude,
        longitude: _longitude,
      );
      _warning = warning;
      _loading = false;
      _loaded = true;
    });
  }

  String _label(SeismicEvent event) {
    final distance = reportEventDistance(event, _latitude, _longitude);
    final time = event.detectedAt.toLocal();
    final date =
        '${time.day}/${time.month} ${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
    return '${event.place ?? 'Ubicación no determinada'} · $date'
        '${event.magnitude == null ? '' : ' · M${event.magnitude!.toStringAsFixed(1)}'}'
        '${distance == null ? '' : ' · ${distance.round()} km de tu ubicación'}';
  }

  Future<void> _pick() async {
    if (!_loaded) await _load();
    if (!mounted || _events.isEmpty) return;
    final event = await Navigator.of(context).push<SeismicEvent>(
      adaptiveRoute<SeismicEvent>(
        (pageContext) => AdaptiveScreen(
          title: 'Selecciona el sismo',
          child: ListView(
            children: <Widget>[
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Sismos de los últimos 7 días. Verifica lugar y hora; cercanía no significa que lo hayas sentido.',
                ),
              ),
              for (final event in _events)
                if (usesCupertino)
                  CupertinoListTile(
                    title: Text(_label(event), maxLines: 4),
                    subtitle: Text(event.agency ?? 'Seismik · preliminar'),
                    onTap: () => Navigator.pop(pageContext, event),
                  )
                else
                  ListTile(
                    title: Text(_label(event)),
                    subtitle: Text(event.agency ?? 'Seismik · preliminar'),
                    onTap: () => Navigator.pop(pageContext, event),
                  ),
            ],
          ),
        ),
        title: 'Selecciona el sismo',
      ),
    );
    if (event == null || !mounted) return;
    setState(() => _selected = event);
    widget.onSelected(event);
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        const Text(
          '1. Selecciona el sismo',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
        Text(
          !_loaded
              ? 'Al buscar, usa tu ubicación para ordenar los sismos cercanos.'
              : _latitude == null
              ? 'Sin ubicación: se ordenan por fecha. Activa la ubicación y actualiza para ver los más cercanos.'
              : 'Ordenados por distancia a tu ubicación actual. Comprueba que estabas allí cuando ocurrió.',
        ),
        if (_warning != null) Text(_warning!),
        if (_selected != null) Text(_label(_selected!)),
        const SizedBox(height: 8),
        AdaptiveButton(
          label: _loading
              ? 'Buscando sismos…'
              : _selected == null
              ? 'Elegir sismo'
              : 'Cambiar sismo',
          onPressed: !widget.enabled || _loading || (_loaded && _events.isEmpty)
              ? null
              : _pick,
        ),
        if (_loaded && !_loading && _events.isEmpty)
          const Text(
            'No hay sismos recientes disponibles. Actualiza o vuelve más tarde; no se enviará un reporte sin sismo.',
          ),
        AdaptiveButton(
          label: 'Actualizar sismos y ubicación',
          kind: AdaptiveButtonKind.tinted,
          onPressed: !widget.enabled || _loading ? null : _load,
        ),
      ],
    ),
  );
}
