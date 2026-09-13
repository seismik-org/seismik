import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:provider/provider.dart';

import '../../services/map_launcher.dart';
import '../../state/mobile_settings.dart';
import '../../state/seismik_state.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({required this.dynamicColorAvailable, super.key});

  final bool dynamicColorAvailable;

  static const Map<String, String> _historySources = <String, String>{
    'seismik_seedlink_preliminary': 'Seismik / SeedLink · Preliminar',
    'sgc_colombia': 'SGC · Colombia',
    'usgs_global': 'USGS · Global',
    'igp_peru': 'IGP · Perú',
    'ingv_italy': 'INGV · Italia',
    'geonet_new_zealand': 'GeoNet · Nueva Zelanda',
    'bmkg_indonesia': 'BMKG · Indonesia',
    'jma_japan': 'JMA · Japón',
  };

  @override
  Widget build(BuildContext context) {
    final MobileSettings settings = context.watch<MobileSettings>();
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Configuración')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: <Widget>[
          const _Header(),
          const SizedBox(height: 12),
          _Section(
            title: 'Alertas críticas',
            icon: Icons.notification_important_outlined,
            children: <Widget>[
              ListTile(
                leading: const Icon(Icons.fullscreen_rounded),
                title: const Text('Autorizar pantalla completa'),
                subtitle: const Text(
                  'Necesario en Android 14+ para abrir la guía con la pantalla bloqueada o apagada. Desbloqueado, Android puede mostrar un banner.',
                ),
                trailing: const Icon(Icons.open_in_new_rounded),
                onTap: () async {
                  final bool granted = await context
                      .read<SeismikState>()
                      .notifications
                      .requestCriticalAlertAccess();
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          granted
                              ? 'Pantalla completa autorizada.'
                              : 'Activa “Permitir alertas a pantalla completa” para Seismik.',
                        ),
                      ),
                    );
                  }
                },
              ),
              ListTile(
                leading: const Icon(Icons.crisis_alert_rounded),
                title: const Text('Probar alerta en este teléfono'),
                subtitle: const Text(
                  'Ejecuta una simulación local. No reporta un sismo ni avisa a otros usuarios.',
                ),
                trailing: const Icon(Icons.play_arrow_rounded),
                onTap: () => unawaited(
                  context
                      .read<SeismikState>()
                      .notifications
                      .runCriticalAlertTest(),
                ),
              ),
              SwitchListTile.adaptive(
                value: settings.receiveEarlyAlerts,
                onChanged: (value) =>
                    unawaited(settings.setReceiveEarlyAlerts(value)),
                title: const Text('Alertas tempranas'),
                subtitle: const Text(
                  'Avisos técnicos multiestación cercanos. Pueden llegar antes del reporte oficial.',
                ),
              ),
              SwitchListTile.adaptive(
                value: settings.receiveOfficialUpdates,
                onChanged: (value) =>
                    unawaited(settings.setReceiveOfficialUpdates(value)),
                title: const Text('Actualizaciones oficiales'),
                subtitle: const Text(
                  'Magnitud, profundidad y fuente publicada por una entidad geológica.',
                ),
              ),
              _NotificationMagnitudeSlider(settings: settings),
              _AlertRadiusSelector(settings: settings),
            ],
          ),
          const SizedBox(height: 12),
          _Section(
            title: 'Mapas y sincronización',
            icon: Icons.map_outlined,
            children: <Widget>[
              ListTile(
                title: const Text('Abrir epicentros con'),
                subtitle: const Text(
                  'Se usa al tocar «Abrir epicentro» en un sismo. Si la app '
                  'elegida no está instalada, se abre la versión web.',
                ),
                trailing: DropdownButton<MapProvider>(
                  value: settings.mapProvider,
                  onChanged: (value) => unawaited(
                    settings.setMapProvider(value ?? MapProvider.system),
                  ),
                  items: MapProvider.values
                      .where(
                        (provider) =>
                            provider != MapProvider.apple ||
                            Platform.isIOS ||
                            Platform.isMacOS,
                      )
                      .map(
                        (provider) => DropdownMenuItem<MapProvider>(
                          value: provider,
                          child: Text(provider.label),
                        ),
                      )
                      .toList(growable: false),
                ),
              ),
              const _PendingReportsTile(),
            ],
          ),
          const SizedBox(height: 12),
          _Section(
            title: 'Apariencia',
            icon: Icons.palette_outlined,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
                child: SegmentedButton<ThemeMode>(
                  segments: const <ButtonSegment<ThemeMode>>[
                    ButtonSegment(
                      value: ThemeMode.system,
                      icon: Icon(Icons.settings_brightness),
                      label: Text('Sistema'),
                    ),
                    ButtonSegment(
                      value: ThemeMode.light,
                      icon: Icon(Icons.light_mode_outlined),
                      label: Text('Claro'),
                    ),
                    ButtonSegment(
                      value: ThemeMode.dark,
                      icon: Icon(Icons.dark_mode_outlined),
                      label: Text('Oscuro'),
                    ),
                  ],
                  selected: <ThemeMode>{settings.themeMode},
                  onSelectionChanged: (selection) =>
                      unawaited(settings.setThemeMode(selection.single)),
                ),
              ),
              SwitchListTile.adaptive(
                value: settings.useDynamicColor,
                onChanged: dynamicColorAvailable
                    ? (value) => unawaited(settings.setUseDynamicColor(value))
                    : null,
                title: const Text('Colores dinámicos Material You'),
                subtitle: Text(
                  dynamicColorAvailable
                      ? 'Usa la paleta completa publicada por Android/One UI.'
                      : 'Android no publicó una paleta dinámica en este dispositivo.',
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Wrap(
                  spacing: 8,
                  children:
                      <Color>[
                            colors.primary,
                            colors.secondary,
                            colors.tertiary,
                            colors.surfaceContainerHighest,
                          ]
                          .map(
                            (color) => Tooltip(
                              message: _hex(color),
                              child: CircleAvatar(
                                backgroundColor: color,
                                radius: 16,
                              ),
                            ),
                          )
                          .toList(growable: false),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _Section(
            title: 'Diagnóstico de la beta',
            icon: Icons.science_outlined,
            children: <Widget>[
              FutureBuilder<String>(
                future: context.read<SeismikState>().api.ensureDeviceId(),
                builder: (context, snapshot) => ListTile(
                  title: const Text('Identificador de este dispositivo'),
                  subtitle: Text(snapshot.data ?? 'Preparando…'),
                  trailing: snapshot.hasData
                      ? IconButton(
                          tooltip: 'Copiar identificador',
                          icon: const Icon(Icons.copy_rounded),
                          onPressed: () async {
                            await Clipboard.setData(
                              ClipboardData(text: snapshot.data!),
                            );
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Identificador copiado'),
                                ),
                              );
                            }
                          },
                        )
                      : null,
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Text(
                  'Este identificador permite incluir el teléfono en la lista cerrada de pruebas push. No es un dato personal.',
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _Section(
            title: 'Historial sísmico',
            icon: Icons.public_rounded,
            children: <Widget>[
              _MagnitudeSlider(settings: settings),
              ListTile(
                title: const Text('Periodo del historial'),
                trailing: DropdownButton<int>(
                  value: settings.historyDays,
                  items: const <DropdownMenuItem<int>>[
                    DropdownMenuItem(value: 1, child: Text('24 horas')),
                    DropdownMenuItem(value: 7, child: Text('7 días')),
                    DropdownMenuItem(value: 14, child: Text('14 días')),
                    DropdownMenuItem(value: 30, child: Text('30 días')),
                  ],
                  onChanged: (value) {
                    if (value != null) {
                      unawaited(settings.setHistoryDays(value));
                    }
                  },
                ),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 8, 16, 4),
                child: Text(
                  'Fuentes del historial',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
              for (final MapEntry<String, String> source
                  in _historySources.entries)
                CheckboxListTile(
                  dense: true,
                  value: settings.historySources.contains(source.key),
                  title: Text(source.value),
                  subtitle: switch (source.key) {
                    'usgs_global' => const Text(
                      'Cobertura mundial de respaldo',
                    ),
                    'seismik_seedlink_preliminary' => const Text(
                      'Detección automática STA/LTA multiestación. No es un reporte oficial ni asigna magnitud sin cálculo confiable.',
                    ),
                    _ => null,
                  },
                  onChanged: (selected) => unawaited(
                    settings.setHistorySource(source.key, selected ?? false),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          _Section(
            title: 'Privacidad y sensores',
            icon: Icons.shield_outlined,
            children: <Widget>[
              SwitchListTile.adaptive(
                value: settings.crowdsourcingEnabled,
                onChanged: (value) =>
                    unawaited(settings.setCrowdsourcingEnabled(value)),
                title: const Text('Detección colaborativa'),
                subtitle: const Text(
                  'Activa o detiene realmente el acelerómetro de Seismik.',
                ),
              ),
              SwitchListTile.adaptive(
                value: settings.preciseLocationByDefault,
                onChanged: (value) =>
                    unawaited(settings.setPreciseLocationByDefault(value)),
                title: const Text('Ubicación precisa en reportes'),
                subtitle: const Text(
                  'Desactivada por defecto: se conserva una ubicación aproximada.',
                ),
              ),
              ListTile(
                leading: const Icon(Icons.admin_panel_settings_outlined),
                title: const Text('Permisos del sistema'),
                subtitle: const Text('Ubicación, sensores y notificaciones'),
                trailing: const Icon(Icons.open_in_new_rounded),
                onTap: Geolocator.openAppSettings,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'Los cambios quedan guardados en el teléfono y se aplican inmediatamente. '
            'Seismik continúa en beta experimental y no sustituye a las autoridades.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  static String _hex(Color color) =>
      '#${color.toARGB32().toRadixString(16).padLeft(8, '0').substring(2).toUpperCase()}';
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Row(
        children: <Widget>[
          Image.asset('assets/images/seismik_logo.png', width: 58, height: 58),
          const SizedBox(width: 14),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Seismik',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
                ),
                Text('Beta experimental 0.6.6'),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.icon,
    required this.children,
  });
  final String title;
  final IconData icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ListTile(
          leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
          title: Text(
            title,
            style: const TextStyle(fontWeight: FontWeight.w900),
          ),
        ),
        ...children,
      ],
    ),
  );
}

class _MagnitudeSlider extends StatefulWidget {
  const _MagnitudeSlider({required this.settings});
  final MobileSettings settings;

  @override
  State<_MagnitudeSlider> createState() => _MagnitudeSliderState();
}

class _NotificationMagnitudeSlider extends StatefulWidget {
  const _NotificationMagnitudeSlider({required this.settings});
  final MobileSettings settings;

  @override
  State<_NotificationMagnitudeSlider> createState() =>
      _NotificationMagnitudeSliderState();
}

class _NotificationMagnitudeSliderState
    extends State<_NotificationMagnitudeSlider> {
  late double _value = widget.settings.minimumNotificationMagnitude;

  @override
  Widget build(BuildContext context) => ListTile(
    title: const Text('Magnitud mínima para aviso oficial'),
    subtitle: Slider(
      value: _value,
      min: 2,
      max: 8,
      divisions: 12,
      label: 'M ${_value.toStringAsFixed(1)}',
      onChanged: (value) => setState(() => _value = value),
      onChangeEnd: (value) =>
          unawaited(widget.settings.setMinimumNotificationMagnitude(value)),
    ),
    trailing: Text('M ${_value.toStringAsFixed(1)}'),
  );
}

class _MagnitudeSliderState extends State<_MagnitudeSlider> {
  late double _value = widget.settings.minimumHistoryMagnitude;

  @override
  void didUpdateWidget(covariant _MagnitudeSlider oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.settings.minimumHistoryMagnitude !=
        widget.settings.minimumHistoryMagnitude) {
      _value = widget.settings.minimumHistoryMagnitude;
    }
  }

  @override
  Widget build(BuildContext context) => ListTile(
    title: Text('Magnitud mínima: M ${_value.toStringAsFixed(1)}'),
    subtitle: Slider(
      value: _value,
      min: 0,
      max: 7,
      divisions: 14,
      label: _value.toStringAsFixed(1),
      onChanged: (value) => setState(() => _value = value),
      onChangeEnd: (value) =>
          unawaited(widget.settings.setMinimumHistoryMagnitude(value)),
    ),
  );
}

/// Umbral de cercanía: sólo llegan avisos cuyo epicentro esté dentro del radio.
class _AlertRadiusSelector extends StatelessWidget {
  const _AlertRadiusSelector({required this.settings});

  final MobileSettings settings;

  @override
  Widget build(BuildContext context) => ListTile(
    title: const Text('Umbral de cercanía'),
    subtitle: Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        children: MobileSettings.alertRadiusOptions
            .map(
              (radius) => ChoiceChip(
                label: Text('${radius.toStringAsFixed(0)} km'),
                selected: settings.alertRadiusKm == radius,
                onSelected: (selected) {
                  if (selected) unawaited(settings.setAlertRadiusKm(radius));
                },
              ),
            )
            .toList(growable: false),
      ),
    ),
    isThreeLine: true,
  );
}

/// Estado de la cola de reportes creados sin conexión.
class _PendingReportsTile extends StatelessWidget {
  const _PendingReportsTile();

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    final int pending = state.pendingReportCount;
    return ListTile(
      leading: Icon(
        pending > 0 ? Icons.cloud_upload_outlined : Icons.cloud_done_outlined,
      ),
      title: const Text('Reportes sin enviar'),
      subtitle: Text(
        pending == 0
            ? state.syncMessage ?? 'No hay reportes pendientes.'
            : (pending == 1
                  ? '1 reporte guardado se enviará al recuperar la conexión.'
                  : '$pending reportes guardados se enviarán al recuperar la conexión.'),
      ),
      trailing: pending == 0
          ? null
          : TextButton(
              onPressed: () => unawaited(state.flushPendingReports()),
              child: const Text('Enviar ahora'),
            ),
    );
  }
}
