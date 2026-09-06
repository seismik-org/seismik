import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../../core/theme.dart';
import '../widgets/adaptive.dart';
import '../widgets/liquid_glass.dart';

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
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return AdaptiveScreen(
        title: 'Reportar daños',
        child: ListView(
          padding: const EdgeInsets.only(bottom: 36),
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: LiquidGlassCard(
                borderRadius: 18,
                padding: const EdgeInsets.all(14),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Icon(
                      CupertinoIcons.exclamationmark_triangle_fill,
                      color: _urgent ? SeismikColors.crimson : SeismikColors.amber,
                      size: 24,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Seismik no es un servicio de emergencias. Si hay personas heridas, atrapadas, incendio, fuga de gas o riesgo de colapso, llama al número local de emergencias.',
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.35,
                          fontWeight: FontWeight.w600,
                          color: CupertinoColors.label.resolveFrom(context),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('NIVEL DE DAÑO OBSERVADO'),
              children: const <String, String>{
                'none': 'Sin daño visible',
                'minor': 'Menor (grietas superficiales)',
                'moderate': 'Moderado (desprendimientos)',
                'severe': 'Severo (daño estructural)',
                'collapse': 'Colapso parcial o total',
              }.entries.map((entry) => CupertinoListTile(
                title: Text(entry.value),
                trailing: _severity == entry.key
                    ? const Icon(CupertinoIcons.checkmark_circle_fill, color: CupertinoColors.activeBlue)
                    : const Icon(CupertinoIcons.circle, color: CupertinoColors.tertiaryLabel),
                onTap: () {
                  unawaited(HapticFeedback.selectionClick());
                  setState(() => _severity = entry.key);
                },
              )).toList(),
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('PELIGROS OBSERVADOS'),
              children: _hazardLabels.entries.map((entry) => CupertinoListTile(
                title: Text(entry.value),
                trailing: Icon(
                  _hazards.contains(entry.key)
                      ? CupertinoIcons.checkmark_circle_fill
                      : CupertinoIcons.circle,
                  color: _hazards.contains(entry.key)
                      ? CupertinoColors.activeBlue
                      : CupertinoColors.tertiaryLabel,
                  size: 22,
                ),
                onTap: () {
                  unawaited(HapticFeedback.selectionClick());
                  setState(() {
                    if (_hazards.contains(entry.key)) {
                      _hazards.remove(entry.key);
                    } else {
                      _hazards.add(entry.key);
                    }
                  });
                },
              )).toList(),
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('SITUACIÓN CRÍTICA'),
              children: <Widget>[
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
                CupertinoListTile(
                  title: const Text('¿Es seguro permanecer allí?'),
                  additionalInfo: Text(
                    _safeToRemain == null
                        ? 'No estoy seguro'
                        : (_safeToRemain! ? 'Sí' : 'No'),
                  ),
                  trailing: const CupertinoListTileChevron(),
                  onTap: () => _chooseSafeToRemain(context),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('DESCRIPCIÓN DEL LUGAR'),
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  child: CupertinoTextField(
                    controller: _building,
                    maxLength: 80,
                    placeholder: 'Tipo de edificio o infraestructura…',
                    decoration: null,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  child: CupertinoTextField(
                    controller: _comment,
                    maxLength: 1000,
                    maxLines: 3,
                    placeholder: 'Descripción (no incluyas datos personales)…',
                    decoration: null,
                  ),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('UBICACIÓN Y ENVÍO'),
              children: <Widget>[
                CupertinoFormRow(
                  prefix: const Text('País (código ISO)'),
                  child: SizedBox(
                    width: 70,
                    child: CupertinoTextField(
                      controller: _country,
                      maxLength: 2,
                      textAlign: TextAlign.end,
                      textCapitalization: TextCapitalization.characters,
                      placeholder: 'CO',
                      decoration: null,
                    ),
                  ),
                ),
                CupertinoFormRow(
                  prefix: const Text('Ubicación precisa'),
                  helper: const Text('Desactivado: precisión reducida'),
                  child: CupertinoSwitch(
                    value: _precise,
                    onChanged: (value) => setState(() => _precise = value),
                  ),
                ),
                CupertinoFormRow(
                  prefix: const Text('Mostrar formularios oficiales'),
                  child: CupertinoSwitch(
                    value: _official,
                    onChanged: (value) => setState(() => _official = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: AdaptiveButton(
                kind: _urgent
                    ? AdaptiveButtonKind.destructive
                    : AdaptiveButtonKind.primary,
                onPressed: _submitting ? null : _submit,
                icon: Icons.send,
                label: _submitting ? 'Enviando…' : 'Enviar reporte a Seismik',
              ),
            ),
          ],
        ),
      );
    }

    return AdaptiveScreen(
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
  }

  void _chooseSafeToRemain(BuildContext context) {
    showCupertinoModalPopup<void>(
      context: context,
      builder: (sheetContext) => CupertinoActionSheet(
        title: const Text('¿Es seguro permanecer allí?'),
        actions: <Widget>[
          CupertinoActionSheetAction(
            onPressed: () {
              setState(() => _safeToRemain = true);
              Navigator.pop(sheetContext);
            },
            child: const Text('Sí, es seguro'),
          ),
          CupertinoActionSheetAction(
            onPressed: () {
              setState(() => _safeToRemain = false);
              Navigator.pop(sheetContext);
            },
            child: const Text('No es seguro'),
          ),
          CupertinoActionSheetAction(
            onPressed: () {
              setState(() => _safeToRemain = null);
              Navigator.pop(sheetContext);
            },
            child: const Text('No estoy seguro'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          onPressed: () => Navigator.pop(sheetContext),
          child: const Text('Cancelar'),
        ),
      ),
    );
  }

  Widget _check(String label, bool value, ValueChanged<bool> update) {
    if (usesCupertino) {
      return CupertinoListTile(
        title: Text(label),
        trailing: Icon(
          value
              ? CupertinoIcons.checkmark_circle_fill
              : CupertinoIcons.circle,
          color: value ? CupertinoColors.activeBlue : CupertinoColors.tertiaryLabel,
          size: 22,
        ),
        onTap: () {
          unawaited(HapticFeedback.selectionClick());
          setState(() => update(!value));
        },
      );
    }
    return CheckboxListTile(
      value: value,
      onChanged: (next) => setState(() => update(next ?? false)),
      title: Text(label),
    );
  }
}

