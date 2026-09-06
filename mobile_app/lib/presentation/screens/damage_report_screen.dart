import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../widgets/adaptive.dart';
import '../../data/models/citizen_report.dart';
import '../../data/models/pending_report.dart';
import '../../data/models/seismic_event.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
import 'report_result_screen.dart';

class DamageReportScreen extends StatefulWidget {
  const DamageReportScreen({this.event, super.key});
  final SeismicEvent? event;

  @override
  State<DamageReportScreen> createState() => _DamageReportScreenState();
}

class _DamageReportScreenState extends State<DamageReportScreen> {
  static const Map<String, String> _hazardLabels = <String, String>{
    'fire': 'Incendio',
    'gas_leak': 'Fuga de gas',
    'electrical': 'Riesgo eléctrico',
    'water_leak': 'Fuga de agua',
    'landslide': 'Deslizamiento',
    'road_blocked': 'Vía bloqueada',
    'structural_instability': 'Estructura inestable',
  };

  final TextEditingController _comment = TextEditingController();
  final TextEditingController _building = TextEditingController();
  final TextEditingController _country = TextEditingController();
  final Set<String> _hazards = <String>{};
  String _severity = 'minor';
  bool _peopleTrapped = false;
  bool _injuries = false;
  bool _emergencyContacted = false;
  bool? _safeToRemain;
  bool _precise = false;
  bool _official = true;
  bool _submitting = false;
  bool _settingsLoaded = false;

  @override
  void initState() {
    super.initState();
    _country.text =
        widget.event?.countryCode ??
        WidgetsBinding.instance.platformDispatcher.locale.countryCode ??
        'CO';
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_settingsLoaded) return;
    _precise = context.read<MobileSettings>().preciseLocationByDefault;
    _settingsLoaded = true;
  }

  @override
  void dispose() {
    _comment.dispose();
    _building.dispose();
    _country.dispose();
    super.dispose();
  }

  bool get _urgent =>
      _peopleTrapped ||
      _injuries ||
      _severity == 'severe' ||
      _severity == 'collapse' ||
      _hazards.contains('fire') ||
      _hazards.contains('gas_leak');

  Future<void> _submit() async {
    if (_country.text.trim().length != 2) {
      await showAdaptiveNotice(
        context,
        message: 'Usa un código de país de dos letras.',
      );
      return;
    }
    setState(() => _submitting = true);
    try {
      final SeismikState state = context.read<SeismikState>();
      final ({double latitude, double longitude})? coordinates = await state
          .currentCoordinates();
      if (coordinates == null) throw Exception('No hay ubicación disponible');
      final Map<String, dynamic> payload = await state.api.buildDamageReport(
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
        countryCode: _country.text,
        preciseLocation: _precise,
        shareWithOfficialAgencies: _official,
        severity: _severity,
        hazards: _hazards.toList(growable: false),
        peopleTrapped: _peopleTrapped,
        injuriesObserved: _injuries,
        emergencyServicesContacted: _emergencyContacted,
        safeToRemain: _safeToRemain,
        earthquakeEventId: widget.event?.id,
        officialEventId: widget.event?.officialEventId,
        buildingType: _building.text,
        comment: _comment.text,
      );
      final ReportResult result = await state.submitReport(
        kind: PendingReportKind.damage,
        payload: payload,
        preciseLocation: _precise,
        emergencyActionRecommended: _urgent,
      );
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(
        adaptiveRoute<void>(
          (_) => ReportResultScreen(result: result),
          title: 'Reporte',
        ),
      );
    } catch (error) {
      if (mounted) {
        await showAdaptiveNotice(context, message: 'No se pudo enviar: $error');
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => AdaptiveScreen(
    title: 'Reportar daños',
    child: ListView(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 28),
      children: <Widget>[
        Card(
          color: _urgent ? const Color(0xFF7A1717) : const Color(0xFF49330B),
          child: const Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.warning_amber_rounded),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Seismik no es un servicio de emergencias. Si hay personas heridas o atrapadas, incendio, fuga de gas o riesgo de colapso, aléjate del peligro y llama al número local de emergencias.',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _severity,
          decoration: const InputDecoration(
            labelText: 'Daño observado',
            border: OutlineInputBorder(),
          ),
          items: const <DropdownMenuItem<String>>[
            DropdownMenuItem(value: 'none', child: Text('Sin daño visible')),
            DropdownMenuItem(value: 'minor', child: Text('Menor')),
            DropdownMenuItem(value: 'moderate', child: Text('Moderado')),
            DropdownMenuItem(value: 'severe', child: Text('Severo')),
            DropdownMenuItem(value: 'collapse', child: Text('Colapso')),
          ],
          onChanged: (value) => setState(() => _severity = value ?? 'minor'),
        ),
        const SizedBox(height: 18),
        Text(
          'Peligros observados',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: _hazardLabels.entries
              .map(
                (entry) => FilterChip(
                  label: Text(entry.value),
                  selected: _hazards.contains(entry.key),
                  onSelected: (selected) => setState(() {
                    selected
                        ? _hazards.add(entry.key)
                        : _hazards.remove(entry.key);
                  }),
                ),
              )
              .toList(growable: false),
        ),
        const SizedBox(height: 12),
        _check(
          'Hay personas atrapadas',
          _peopleTrapped,
          (v) => _peopleTrapped = v,
        ),
        _check('Hay personas heridas', _injuries, (v) => _injuries = v),
        _check(
          'Ya contacté a emergencias',
          _emergencyContacted,
          (v) => _emergencyContacted = v,
        ),
        DropdownButtonFormField<bool?>(
          initialValue: _safeToRemain,
          decoration: const InputDecoration(
            labelText: '¿Es seguro permanecer allí?',
          ),
          items: const <DropdownMenuItem<bool?>>[
            DropdownMenuItem(value: null, child: Text('No estoy seguro')),
            DropdownMenuItem(value: true, child: Text('Sí')),
            DropdownMenuItem(value: false, child: Text('No')),
          ],
          onChanged: (value) => setState(() => _safeToRemain = value),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _building,
          maxLength: 80,
          decoration: const InputDecoration(
            labelText: 'Tipo de edificio o infraestructura',
            border: OutlineInputBorder(),
          ),
        ),
        TextField(
          controller: _comment,
          maxLength: 1000,
          maxLines: 4,
          decoration: const InputDecoration(
            labelText: 'Descripción (no incluyas datos personales)',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: <Widget>[
                TextField(
                  controller: _country,
                  maxLength: 2,
                  textCapitalization: TextCapitalization.characters,
                  decoration: const InputDecoration(
                    labelText: 'País (ISO, ej. CO)',
                  ),
                ),
                SwitchListTile.adaptive(
                  value: _precise,
                  onChanged: (value) => setState(() => _precise = value),
                  title: const Text('Compartir ubicación precisa'),
                  subtitle: const Text(
                    'Por defecto se guarda una ubicación aproximada.',
                  ),
                ),
                SwitchListTile.adaptive(
                  value: _official,
                  onChanged: (value) => setState(() => _official = value),
                  title: const Text('Mostrar formularios oficiales'),
                  subtitle: const Text(
                    'Se abren aparte y tú decides si enviarlos.',
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),
        AdaptiveButton(
          kind: _urgent
              ? AdaptiveButtonKind.destructive
              : AdaptiveButtonKind.primary,
          onPressed: _submitting ? null : _submit,
          icon: Icons.send,
          label: _submitting ? 'Enviando…' : 'Enviar reporte a Seismik',
        ),
        const SizedBox(height: 24),
      ],
    ),
  );

  /// En iPhone estos controles son interruptores; en Android, casillas.
  Widget _check(String label, bool value, ValueChanged<bool> update) =>
      usesCupertino
      ? SwitchListTile.adaptive(
          dense: true,
          value: value,
          onChanged: (next) => setState(() => update(next)),
          title: Text(label),
        )
      : CheckboxListTile(
        value: value,
        onChanged: (next) => setState(() => update(next ?? false)),
        title: Text(label),
      );
}
