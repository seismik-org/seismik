import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../data/models/seismic_event.dart';
import '../../services/map_launcher.dart';
import '../../state/mobile_settings.dart';

/// Abre el epicentro de un sismo en la app de mapas preferida.
///
/// No se muestra cuando el evento aún no tiene epicentro estimado: un candidato
/// sin localizar no puede señalarse en un mapa sin inventar una posición.
class OpenInMapsButton extends StatelessWidget {
  const OpenInMapsButton({
    required this.event,
    this.launcher = const MapLauncher(),
    this.compact = false,
    super.key,
  });

  final SeismicEvent event;
  final MapLauncher launcher;
  final bool compact;

  bool get _hasEpicenter => event.latitude != null && event.longitude != null;

  Future<void> _open(BuildContext context) async {
    final MapProvider provider = context.read<MobileSettings>().mapProvider;
    final ScaffoldMessengerState? messenger = ScaffoldMessenger.maybeOf(
      context,
    );
    final bool opened = await launcher.openEpicenter(
      latitude: event.latitude!,
      longitude: event.longitude!,
      label: event.place ?? 'Epicentro',
      provider: provider,
    );
    if (!opened) {
      messenger?.showSnackBar(
        const SnackBar(
          content: Text('No hay una aplicación de mapas disponible.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_hasEpicenter) return const SizedBox.shrink();
    final Icon icon = const Icon(Icons.map_outlined);
    final Text label = Text(_label(context));
    return compact
        ? TextButton.icon(
            onPressed: () => _open(context),
            icon: icon,
            label: label,
          )
        : OutlinedButton.icon(
            onPressed: () => _open(context),
            icon: icon,
            label: label,
          );
  }

  String _label(BuildContext context) {
    final MapProvider provider = context.watch<MobileSettings>().mapProvider;
    if (provider == MapProvider.apple &&
        !(Platform.isIOS || Platform.isMacOS)) {
      return 'Abrir epicentro en mapas';
    }
    return switch (provider) {
      MapProvider.google => 'Abrir en Google Maps',
      MapProvider.apple => 'Abrir en Apple Maps',
      MapProvider.system => 'Abrir epicentro en mapas',
    };
  }
}
