import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../services/map_launcher.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';

/// Settings designed for iPhone: grouped lists, Cupertino controls and action
/// sheets. Android continues using its Material/One UI settings screen.
class IosSettingsScreen extends StatelessWidget {
  const IosSettingsScreen({required this.dynamicColorAvailable, super.key});

  final bool dynamicColorAvailable;

  @override
  Widget build(BuildContext context) {
    final MobileSettings settings = context.watch<MobileSettings>();
    return CupertinoPageScaffold(
      navigationBar: const CupertinoNavigationBar(
        middle: Text('Configuración'),
      ),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.only(bottom: 24),
          children: <Widget>[
            const _AccountHeader(),
            CupertinoListSection.insetGrouped(
              header: const Text('ALERTAS SÍSMICAS'),
              footer: const Text(
                'Las alertas tempranas son estimaciones técnicas cercanas. '
                'Contrasta siempre con las autoridades locales.',
              ),
              children: <Widget>[
                _SwitchRow(
                  label: 'Alertas tempranas',
                  value: settings.receiveEarlyAlerts,
                  onChanged: (value) => unawaited(
                    settings.setReceiveEarlyAlerts(value),
                  ),
                ),
                _SwitchRow(
                  label: 'Actualizaciones oficiales',
                  value: settings.receiveOfficialUpdates,
                  onChanged: (value) => unawaited(
                    settings.setReceiveOfficialUpdates(value),
                  ),
                ),
                CupertinoListTile(
                  title: const Text('Magnitud mínima'),
                  additionalInfo: Text(
                    'M ${settings.minimumNotificationMagnitude.toStringAsFixed(1)}',
                  ),
                  trailing: const CupertinoListTileChevron(),
                  onTap: () => _showMagnitude(context, settings),
                ),
                CupertinoListTile(
                  title: const Text('Radio de alerta'),
                  additionalInfo: Text(
                    '${settings.alertRadiusKm.toStringAsFixed(0)} km',
                  ),
                  trailing: const CupertinoListTileChevron(),
                  onTap: () => _showRadius(context, settings),
                ),
                CupertinoListTile(
                  title: const Text('Probar alerta'),
                  subtitle: const Text('Sólo en este iPhone; no avisa a otras personas.'),
                  trailing: const CupertinoListTileChevron(),
                  onTap: () => unawaited(
                    context.read<SeismikState>().notifications.runCriticalAlertTest(),
                  ),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('MAPAS'),
              children: <Widget>[
                CupertinoListTile(
                  title: const Text('Abrir epicentros con'),
                  additionalInfo: Text(settings.mapProvider.label),
                  trailing: const CupertinoListTileChevron(),
                  onTap: () => _showMaps(context, settings),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('PRIVACIDAD Y SENSORES'),
              footer: const Text(
                'La detección colaborativa usa el acelerómetro sólo cuando '
                'está activada. Los reportes usan ubicación aproximada por defecto.',
              ),
              children: <Widget>[
                _SwitchRow(
                  label: 'Detección colaborativa',
                  value: settings.crowdsourcingEnabled,
                  onChanged: (value) => unawaited(
                    settings.setCrowdsourcingEnabled(value),
                  ),
                ),
                _SwitchRow(
                  label: 'Ubicación precisa en reportes',
                  value: settings.preciseLocationByDefault,
                  onChanged: (value) => unawaited(
                    settings.setPreciseLocationByDefault(value),
                  ),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('APARIENCIA'),
              children: <Widget>[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
                  child: CupertinoSlidingSegmentedControl<ThemeMode>(
                    groupValue: settings.themeMode,
                    children: const <ThemeMode, Widget>{
                      ThemeMode.system: Padding(
                        padding: EdgeInsets.symmetric(horizontal: 10),
                        child: Text('Automático'),
                      ),
                      ThemeMode.light: Padding(
                        padding: EdgeInsets.symmetric(horizontal: 10),
                        child: Text('Claro'),
                      ),
                      ThemeMode.dark: Padding(
                        padding: EdgeInsets.symmetric(horizontal: 10),
                        child: Text('Oscuro'),
                      ),
                    },
                    onValueChanged: (value) {
                      if (value != null) unawaited(settings.setThemeMode(value));
                    },
                  ),
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('BETA'),
              children: <Widget>[
                FutureBuilder<String>(
                  future: context.read<SeismikState>().api.ensureDeviceId(),
                  builder: (context, snapshot) => CupertinoListTile(
                    title: const Text('Identificador de este iPhone'),
                    subtitle: Text(snapshot.data ?? 'Preparando…'),
                    trailing: snapshot.hasData
                        ? CupertinoButton(
                            padding: EdgeInsets.zero,
                            onPressed: () => unawaited(
                              Clipboard.setData(ClipboardData(text: snapshot.data!)),
                            ),
                            child: const Icon(CupertinoIcons.doc_on_doc),
                          )
                        : null,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showMagnitude(
    BuildContext context,
    MobileSettings settings,
  ) async {
    double selected = settings.minimumNotificationMagnitude;
    await showCupertinoModalPopup<void>(
      context: context,
      builder: (sheetContext) => CupertinoActionSheet(
        title: const Text('Magnitud mínima'),
        message: StatefulBuilder(
          builder: (context, setState) => Column(
            children: <Widget>[
              Text('M ${selected.toStringAsFixed(1)}'),
              CupertinoSlider(
                value: selected,
                min: 2,
                max: 8,
                divisions: 12,
                onChanged: (value) => setState(() => selected = value),
              ),
            ],
          ),
        ),
        actions: <Widget>[
          CupertinoActionSheetAction(
            onPressed: () {
              unawaited(settings.setMinimumNotificationMagnitude(selected));
              Navigator.pop(sheetContext);
            },
            child: const Text('Guardar'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.pop(sheetContext),
          child: const Text('Cancelar'),
        ),
      ),
    );
  }

  Future<void> _showRadius(BuildContext context, MobileSettings settings) =>
      showCupertinoModalPopup<void>(
        context: context,
        builder: (sheetContext) => CupertinoActionSheet(
          title: const Text('Radio de alerta'),
          actions: MobileSettings.alertRadiusOptions
              .map(
                (radius) => CupertinoActionSheetAction(
                  isDefaultAction: radius == settings.alertRadiusKm,
                  onPressed: () {
                    unawaited(settings.setAlertRadiusKm(radius));
                    Navigator.pop(sheetContext);
                  },
                  child: Text('${radius.toStringAsFixed(0)} km'),
                ),
              )
              .toList(growable: false),
          cancelButton: CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(sheetContext),
            child: const Text('Cancelar'),
          ),
        ),
      );

  Future<void> _showMaps(BuildContext context, MobileSettings settings) =>
      showCupertinoModalPopup<void>(
        context: context,
        builder: (sheetContext) => CupertinoActionSheet(
          title: const Text('Abrir epicentros con'),
          actions: <MapProvider>[
            MapProvider.apple,
            MapProvider.google,
            MapProvider.system,
          ]
              .map(
                (provider) => CupertinoActionSheetAction(
                  isDefaultAction: provider == settings.mapProvider,
                  onPressed: () {
                    unawaited(settings.setMapProvider(provider));
                    Navigator.pop(sheetContext);
                  },
                  child: Text(provider.label),
                ),
              )
              .toList(growable: false),
          cancelButton: CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(sheetContext),
            child: const Text('Cancelar'),
          ),
        ),
      );
}

class _AccountHeader extends StatelessWidget {
  const _AccountHeader();

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(28, 24, 28, 4),
    child: Row(
      children: <Widget>[
        ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: Image.asset('assets/images/seismik_logo.png', width: 64, height: 64),
        ),
        const SizedBox(width: 14),
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Seismik', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
              SizedBox(height: 2),
              Text('Alertas y reportes sísmicos', style: TextStyle(color: CupertinoColors.secondaryLabel)),
            ],
          ),
        ),
      ],
    ),
  );
}

class _SwitchRow extends StatelessWidget {
  const _SwitchRow({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => CupertinoFormRow(
    prefix: Text(label),
    child: CupertinoSwitch(value: value, onChanged: onChanged),
  );
}
