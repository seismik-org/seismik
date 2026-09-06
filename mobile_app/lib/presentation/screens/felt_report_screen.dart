import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/platform.dart';
import '../widgets/adaptive.dart';

import '../../data/models/citizen_report.dart';
import '../../data/models/pending_report.dart';
import '../../data/models/seismic_event.dart';
import '../../services/agency_preference_store.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';
import 'report_result_screen.dart';

class FeltReportScreen extends StatefulWidget {
  const FeltReportScreen({this.event, super.key});
  final SeismicEvent? event;

  @override
  State<FeltReportScreen> createState() => _FeltReportScreenState();
}

class _FeltReportScreenState extends State<FeltReportScreen> {
  final TextEditingController _comment = TextEditingController();
  final TextEditingController _country = TextEditingController();
  bool _felt = true;
  double _intensity = 3;
  bool _indoors = true;
  bool _wokeUp = false;
  bool _difficultyStanding = false;
  bool _objectsMoved = false;
  bool _objectsFell = false;
  bool _visibleDamage = false;
  bool _precise = false;
  bool _official = true;
  bool _submitting = false;
  bool _loadingAgencies = false;
  List<AgencyRoute> _agencies = <AgencyRoute>[];
  Set<String> _selectedAgencyIds = <String>{};
  String? _agencyLoadWarning;
  bool _settingsLoaded = false;

  static const AgencyPreferenceStore _agencyPreferences =
      AgencyPreferenceStore();

  @override
  void initState() {
    super.initState();
    _country.text =
        widget.event?.countryCode ??
        WidgetsBinding.instance.platformDispatcher.locale.countryCode ??
        'CO';
    unawaited(_loadAgencies());
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
    _country.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_country.text.trim().length != 2) {
      await showAdaptiveNotice(
        context,
        message: 'Usa un código de país de dos letras, por ejemplo CO.',
      );
      return;
    }
    if (_official && _selectedAgencyIds.isEmpty) {
      await showAdaptiveNotice(
        context,
        message: 'Selecciona al menos una organización geológica.',
      );
      return;
    }
    setState(() => _submitting = true);
    final SeismikState state = context.read<SeismikState>();
    try {
      await _agencyPreferences.save(
        _preferenceKey,
        _official ? _selectedAgencyIds : <String>{},
      );
      final ({double latitude, double longitude})? coordinates = await state
          .currentCoordinates();
      if (coordinates == null) throw Exception('No hay ubicación disponible');
      final Map<String, dynamic> payload = await state.api.buildFeltReport(
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
        countryCode: _country.text,
        preciseLocation: _precise,
        shareWithOfficialAgencies: _official && _selectedAgencyIds.isNotEmpty,
        selectedAgencyIds: _official ? _selectedAgencyIds : <String>{},
        felt: _felt,
        intensityMmi: _felt ? _intensity.round() : null,
        earthquakeEventId: widget.event?.id,
        officialEventId: widget.event?.officialEventId,
        indoors: _indoors,
        wokeUp: _wokeUp,
        difficultyStanding: _difficultyStanding,
        objectsMoved: _objectsMoved,
        objectsFell: _objectsFell,
        visibleDamage: _visibleDamage,
        comment: _comment.text,
      );
      final ReportResult result = await state.submitReport(
        kind: PendingReportKind.felt,
        payload: payload,
        preciseLocation: _precise,
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

  String get _preferenceKey =>
      widget.event?.id ?? 'manual-${_country.text.trim().toUpperCase()}';

  Future<void> _loadAgencies() async {
    final String country = _country.text.trim().toUpperCase();
    if (country.length != 2) return;
    if (mounted) {
      setState(() {
        _loadingAgencies = true;
        _agencyLoadWarning = null;
      });
    }
    List<AgencyRoute> agencies = OfficialAgencyCatalog.fallbackFor(
      countryCode: country,
      officialEventId: widget.event?.officialEventId,
    );
    try {
      final List<AgencyRoute> remote = await context
          .read<SeismikState>()
          .api
          .fetchReportingAgencies(
            countryCode: country,
            officialEventId: widget.event?.officialEventId,
          );
      if (remote.isNotEmpty) agencies = remote;
    } catch (_) {
      _agencyLoadWarning =
          'Sin conexión: se muestra el catálogo oficial guardado en la app.';
    }
    final Set<String> available = agencies.map((item) => item.agencyId).toSet();
    final Set<String> saved = await _agencyPreferences.load(_preferenceKey);
    final Set<String> selected = saved.intersection(available);
    if (selected.isEmpty && agencies.isNotEmpty) {
      selected.add(agencies.first.agencyId);
    }
    if (!mounted) return;
    setState(() {
      _agencies = agencies;
      _selectedAgencyIds = selected;
      _loadingAgencies = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return AdaptiveScreen(
        title: '¿Sentiste el sismo?',
        child: ListView(
          padding: const EdgeInsets.only(bottom: 32),
          children: <Widget>[
            CupertinoListSection.insetGrouped(
              header: const Text('EXPERIENCIA'),
              children: <Widget>[
                CupertinoFormRow(
                  prefix: const Text('¿Lo sentiste?', style: TextStyle(fontWeight: FontWeight.w500)),
                  child: CupertinoSwitch(
                    value: _felt,
                    onChanged: (value) {
                      unawaited(HapticFeedback.lightImpact());
                      setState(() => _felt = value);
                    },
                  ),
                ),
                if (_felt) ...<Widget>[
                  CupertinoFormRow(
                    prefix: Text(
                      'Intensidad (${_intensity.round()}/10)',
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                    helper: Text(_intensityDescription(_intensity.round())),
                    child: SizedBox(
                      width: 170,
                      child: CupertinoSlider(
                        value: _intensity,
                        min: 1,
                        max: 10,
                        divisions: 9,
                        onChanged: (value) {
                          if (value.round() != _intensity.round()) {
                            unawaited(HapticFeedback.selectionClick());
                          }
                          setState(() => _intensity = value);
                        },
                      ),
                    ),
                  ),
                ],
              ],
            ),
            if (_felt) ...<Widget>[
              CupertinoListSection.insetGrouped(
                header: const Text('EFECTOS PERCIBIDOS'),
                children: <Widget>[
                  _check('Estaba en interiores', _indoors, (v) => _indoors = v),
                  _check('Me despertó', _wokeUp, (v) => _wokeUp = v),
                  _check(
                    'Fue difícil permanecer de pie',
                    _difficultyStanding,
                    (v) => _difficultyStanding = v,
                  ),
                  _check(
                    'Se movieron objetos',
                    _objectsMoved,
                    (v) => _objectsMoved = v,
                  ),
                  _check('Cayeron objetos', _objectsFell, (v) => _objectsFell = v),
                  _check('Vi daños', _visibleDamage, (v) => _visibleDamage = v),
                ],
              ),
            ],
            CupertinoListSection.insetGrouped(
              header: const Text('DESCRIPCIÓN ADICIONAL'),
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  child: CupertinoTextField(
                    controller: _comment,
                    maxLength: 1000,
                    maxLines: 3,
                    placeholder: 'Comentario opcional…',
                    decoration: null,
                  ),
                ),
              ],
            ),
            _privacyControls(),
            const SizedBox(height: 20),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: AdaptiveButton(
                onPressed: _submitting ? null : _submit,
                icon: Icons.send,
                label: _submitting ? 'Enviando…' : 'Enviar a Seismik',
              ),
            ),
          ],
        ),
      );
    }

    return AdaptiveScreen(
      title: '¿Sentiste el sismo?',
      child: ListView(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 28),
        children: <Widget>[
          SwitchListTile.adaptive(
            value: _felt,
            onChanged: (value) => setState(() => _felt = value),
            title: Text(_felt ? 'Sí, lo sentí' : 'No lo sentí'),
            subtitle: const Text(
              'Los reportes negativos también ayudan a estimar la intensidad.',
            ),
          ),
          if (_felt) ...<Widget>[
            const SizedBox(height: 10),
            Text(
              'Intensidad percibida: ${_intensity.round()} / 10',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Slider.adaptive(
              value: _intensity,
              min: 1,
              max: 10,
              divisions: 9,
              label: _intensity.round().toString(),
              onChanged: (value) => setState(() => _intensity = value),
            ),
            Text(
              _intensityDescription(_intensity.round()),
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            _check('Estaba en interiores', _indoors, (v) => _indoors = v),
            _check('Me despertó', _wokeUp, (v) => _wokeUp = v),
            _check(
              'Fue difícil permanecer de pie',
              _difficultyStanding,
              (v) => _difficultyStanding = v,
            ),
            _check(
              'Se movieron objetos',
              _objectsMoved,
              (v) => _objectsMoved = v,
            ),
            _check('Cayeron objetos', _objectsFell, (v) => _objectsFell = v),
            _check('Vi daños', _visibleDamage, (v) => _visibleDamage = v),
          ],
          const SizedBox(height: 12),
          TextField(
            controller: _comment,
            maxLength: 1000,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Comentario opcional',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          _privacyControls(),
          const SizedBox(height: 18),
          AdaptiveButton(
            onPressed: _submitting ? null : _submit,
            icon: Icons.send,
            label: _submitting ? 'Enviando…' : 'Enviar a Seismik',
          ),
          const SizedBox(height: 24),
        ],
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
      dense: true,
      value: value,
      onChanged: (next) => setState(() => update(next ?? false)),
      title: Text(label),
    );
  }

  Widget _privacyControls() {
    if (usesCupertino) {
      return CupertinoListSection.insetGrouped(
        header: const Text('PRIVACIDAD Y DESTINO'),
        footer: const Text(
          'Seismik no suplanta a la entidad oficial. Tras guardar tu reporte se abrirá el formulario elegido.',
        ),
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
                onSubmitted: (_) => _loadAgencies(),
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
            prefix: const Text('Reportar a entidad oficial'),
            child: CupertinoSwitch(
              value: _official,
              onChanged: (value) => setState(() => _official = value),
            ),
          ),
          if (_official) ...<Widget>[
            if (_loadingAgencies)
              const Padding(
                padding: EdgeInsets.all(14),
                child: Center(child: CupertinoActivityIndicator()),
              )
            else
              for (final AgencyRoute agency in _agencies)
                CupertinoListTile(
                  title: Text(agency.agencyName),
                  subtitle: Text(
                    agency.countryCode == null
                        ? 'Cobertura internacional'
                        : 'Entidad de ${agency.countryCode}',
                  ),
                  trailing: Icon(
                    _selectedAgencyIds.contains(agency.agencyId)
                        ? CupertinoIcons.checkmark_circle_fill
                        : CupertinoIcons.circle,
                    color: _selectedAgencyIds.contains(agency.agencyId)
                        ? CupertinoColors.activeBlue
                        : CupertinoColors.tertiaryLabel,
                    size: 22,
                  ),
                  onTap: () {
                    unawaited(HapticFeedback.selectionClick());
                    setState(() {
                      if (_selectedAgencyIds.contains(agency.agencyId)) {
                        _selectedAgencyIds.remove(agency.agencyId);
                      } else {
                        _selectedAgencyIds.add(agency.agencyId);
                      }
                    });
                  },
                ),
          ],
        ],
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: <Widget>[
            TextField(
              controller: _country,
              maxLength: 2,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'País (ISO, ej. CO)'),
              onSubmitted: (_) => _loadAgencies(),
            ),
            SwitchListTile.adaptive(
              value: _precise,
              onChanged: (value) => setState(() => _precise = value),
              title: const Text('Compartir ubicación precisa'),
              subtitle: const Text(
                'Desactivado: Seismik reduce la precisión antes de guardar.',
              ),
            ),
            SwitchListTile.adaptive(
              value: _official,
              onChanged: (value) => setState(() => _official = value),
              title: const Text('Reportar también a una entidad oficial'),
              subtitle: const Text(
                'Tú eliges la organización. Su formulario se abre aparte.',
              ),
            ),
            if (_official) ...<Widget>[
              const Divider(),
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Organización geológica para este sismo',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              const SizedBox(height: 8),
              if (_loadingAgencies)
                const LinearProgressIndicator()
              else
                for (final AgencyRoute agency in _agencies)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _selectedAgencyIds.contains(agency.agencyId),
                    onChanged: (bool? selected) {
                      setState(() {
                        if (selected ?? false) {
                          _selectedAgencyIds.add(agency.agencyId);
                        } else {
                          _selectedAgencyIds.remove(agency.agencyId);
                        }
                      });
                    },
                    title: Text(agency.agencyName),
                    subtitle: Text(
                      agency.countryCode == null
                          ? 'Cobertura internacional'
                          : 'Entidad de ${agency.countryCode}',
                    ),
                  ),
              if (_agencyLoadWarning != null)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    _agencyLoadWarning!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.tertiary,
                    ),
                  ),
                ),
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  'Seismik no suplanta ni envía automáticamente a la entidad. '
                  'Tras guardar tu reporte abrirá el formulario oficial elegido.',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }


  static String _intensityDescription(int value) => switch (value) {
    <= 2 => 'Muy débil: pocas personas lo perciben.',
    <= 4 => 'Leve: vibración clara, objetos pequeños pueden moverse.',
    <= 6 => 'Fuerte: muchas personas se alarman; pueden caer objetos.',
    <= 8 => 'Muy fuerte: posibles daños importantes.',
    _ => 'Extremo: daños severos o colapso. Busca seguridad.',
  };
}
